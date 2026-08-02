# -*- coding: utf-8 -*-
"""
A股日报 → 飞书机器人推送
数据源：腾讯行情(不封IP) + 东财(降级)

腾讯行情字段布局(~分隔，0-indexed)：
  个股: [1]名称 [3]现价 [4]昨收 [31]涨跌额 [32]涨跌幅% [33]最高 [34]最低 [38]换手率 [45]市盈率
  指数: [1]名称 [3]现价 [31]涨跌额 [32]涨跌幅% [6]成交量(手)
"""

import sys, io, json, os, time, re
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 项目根目录 (scripts/tools → scripts → 项目根)
CONFIG_FILE = os.path.join(BASE_DIR, "config", "feishu_config.json")

# 无代理 session
s = requests.Session()
s.trust_env = False


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


# ========== A股代码列表 ==========
def get_a_stock_codes():
    """生成沪深A股代码列表（沪市600/601/603/605, 深市000/001/002/003, 创业板300/301, 科创板688/689）"""
    codes = []
    # 上证主板
    for prefix in ["sh600", "sh601", "sh603", "sh605"]:
        codes.extend([f"{prefix}{i:03d}" for i in range(1, 1000)])
    # 深证主板
    for prefix in ["sz000", "sz001", "sz002", "sz003"]:
        codes.extend([f"{prefix}{i:03d}" for i in range(1, 1000)])
    # 创业板
    for prefix in ["sz300", "sz301"]:
        codes.extend([f"{prefix}{i:03d}" for i in range(1, 1000)])
    # 科创板
    for prefix in ["sh688", "sh689"]:
        codes.extend([f"{prefix}{i:03d}" for i in range(1, 1000)])
    return codes


# ========== 1. 大盘指数（腾讯）==========
def fetch_indices():
    codes = ["sh000001", "sz399001", "sz399006", "sh000688"]
    names = ["上证指数", "深证成指", "创业板指", "科创50"]
    url = "http://qt.gtimg.cn/q=" + ",".join(codes)
    try:
        r = s.get(url, timeout=10)
        r.encoding = "gbk"
        results = []
        for code, name in zip(codes, names):
            m = re.search(rf'v_{re.escape(code)}="([^"]*)"', r.text)
            if not m:
                continue
            f = m.group(1).split("~")
            if len(f) < 33:
                continue
            results.append({
                "name": name, "code": code,
                "price": float(f[3]) if f[3] else 0,
                "change": float(f[31]) if f[31] else 0,
                "change_pct": float(f[32]) if f[32] else 0,
            })
        return results
    except Exception as e:
        print(f"[指数失败] {e}")
        return []


# ========== 2. 涨停板（腾讯批量扫描）==========
def fetch_limit_up_tencent():
    """用腾讯行情批量扫描A股，筛选涨幅>=9.5%的股票"""
    all_codes = get_a_stock_codes()
    zt_list = []
    batch_size = 80
    total_scanned = 0

    print(f"   扫描 {len(all_codes)} 个代码...")

    for i in range(0, len(all_codes), batch_size):
        batch = all_codes[i:i + batch_size]
        url = "http://qt.gtimg.cn/q=" + ",".join(batch)
        try:
            r = s.get(url, timeout=20)
            r.encoding = "gbk"
            # 一次 findall 提取整批数据（替代逐条 regex）
            all_data = dict(re.findall(r'v_(\w+?)="([^"]*)"', r.text))

            for code in batch:
                if code not in all_data:
                    continue
                f = all_data[code].split("~")
                if len(f) < 40 or not f[3]:
                    continue
                try:
                    price = float(f[3])
                    change_pct = float(f[32]) if f[32] else 0
                    if change_pct >= 9.5 and price > 0:
                        preclose = float(f[4]) if f[4] else 0
                        is_20cm = round((price / preclose - 1) * 100, 1) > 19 if preclose > 0 else False
                        zt_list.append({
                            "code": code[2:],
                            "name": f[1],
                            "price": price,
                            "change_pct": change_pct,
                            "turnover": float(f[38]) if len(f) > 38 and f[38] else 0,
                            "is_20cm": is_20cm,
                        })
                except (ValueError, IndexError):
                    continue
            total_scanned += len(batch)
            if i % 800 == 0 and i > 0:
                print(f"   已扫描 {total_scanned}，发现涨停 {len(zt_list)} 只...")
            time.sleep(0.15)  # 避免被腾讯限速
        except Exception as e:
            print(f"   批次{i}失败: {e}")
            time.sleep(1)
            continue

    print(f"   扫描完成: {total_scanned} 个代码")
    return zt_list


# ========== 3. 热门板块（腾讯）==========
def fetch_sectors_tencent():
    """用腾讯板块行情接口，fields[1]=名称 [32]=涨跌幅%"""
    sectors = []
    # 腾讯行业板块代码: pt01801XXX 范围
    sector_codes = [f"pt01801{i:03d}" for i in range(70, 150)]
    url = "http://qt.gtimg.cn/q=" + ",".join(sector_codes)
    try:
        r = s.get(url, timeout=15)
        r.encoding = "gbk"
        # 一次 findall 提取所有板块数据
        all_data = dict(re.findall(r'v_(\w+?)="([^"]*)"', r.text))
        for code in sector_codes:
            if code not in all_data:
                continue
            f = all_data[code].split("~")
            if len(f) < 33 or not f[32]:
                continue
            try:
                pct = float(f[32])  # fields[32] = 涨跌幅%
                name = f[1]
                if name and abs(pct) > 0.01:
                    sectors.append({"name": name, "change_pct": round(pct, 2), "code": code})
            except (ValueError, IndexError):
                continue
        sectors.sort(key=lambda x: x["change_pct"], reverse=True)
    except Exception as e:
        print(f"   [板块失败] {e}")
    return sectors


# ========== 4. 成交额（从腾讯指数数据推算）==========
def fetch_turnover_from_tencent():
    """从上证+深证用腾讯接口直接拿成交额"""
    url = "http://qt.gtimg.cn/q=sh000001,sz399001"
    try:
        r = s.get(url, timeout=10)
        r.encoding = "gbk"
        total_yi = 0
        for code in ["sh000001", "sz399001"]:
            m = re.search(rf'v_{re.escape(code)}="([^"]*)"', r.text)
            if not m:
                continue
            f = m.group(1).split("~")
            if len(f) < 37:
                continue
            # 腾讯QQ行情指数数据中，成交金额约在fields[37]或更深位置
            # 对于指数sh000001，格式中有一个复合字段包含 价格/成交量/成交额
            # 尝试从复合字段或单独字段提取
            # field[35] 可能是 "3867.03/614255215/1258148128160"
            if len(f) > 35 and "/" in (f[35] or ""):
                parts = f[35].split("/")
                if len(parts) >= 3 and parts[2].isdigit():
                    # 第三部分是成交额（元）
                    total_yi += float(parts[2]) / 1e8
        return round(total_yi, 0)
    except Exception as e:
        print(f"   [成交额失败] {e}")
    return 0


# ========== 飞书推送 ==========
def build_feishu_card(indices, zt_list, sectors, turnover, date_str):
    # 大盘
    idx_lines = []
    for idx in indices:
        c = "red" if idx["change_pct"] >= 0 else "green"
        sgn = "+" if idx["change_pct"] >= 0 else ""
        idx_lines.append(
            f"**{idx['name']}**：{idx['price']:.2f}　"
            f"<font color='{c}'>{sgn}{idx['change_pct']:.2f}%　{sgn}{idx['change']:.2f}</font>"
        )

    # 涨停分类
    zt_10 = [z for z in zt_list if not z.get("is_20cm")]
    zt_20 = [z for z in zt_list if z.get("is_20cm")]

    # 板块
    sec_lines = []
    for s in sectors[:10]:
        c = "red" if s["change_pct"] >= 0 else "green"
        sgn = "+" if s["change_pct"] >= 0 else ""
        sec_lines.append(f"<font color='{c}'>{s['name']} {sgn}{s['change_pct']:.2f}%</font>")

    # 涨停龙头
    zt_top = []
    for z in sorted(zt_list, key=lambda x: x.get("change_pct", 0), reverse=True)[:15]:
        tag = "20cm" if z.get("is_20cm") else "涨停"
        t = z.get("turnover", 0)
        zt_top.append(
            f"{z['code']} {z['name']} <font color='red'>+{z['change_pct']:.1f}%</font>"
            f"　[{tag}] 换手{t:.1f}%"
        )

    # 构建各区块
    blocks = [
        "━━━━━━━━━━━━\n**📈 大盘指数**\n" + "\n".join(idx_lines),
        f"\n\n──────────────\n**💰 两市成交额**：{turnover:.0f} 亿" if turnover else "",
    ]

    if sec_lines:
        blocks.append(f"\n\n──────────────\n**🔥 热门板块**\n" + "\n".join(sec_lines))

    if zt_list:
        blocks.append(
            f"\n\n──────────────\n**🎯 涨停板**：{len(zt_list)}只（10cm:{len(zt_10)} | 20cm:{len(zt_20)}）\n"
            + "\n".join(zt_top)
        )

    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"A股日报 | {date_str}"},
                "template": "red",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": "".join(blocks)},
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "数据：腾讯财经 | 每日20:00自动推送 | 仅供参考",
                        }
                    ],
                },
            ],
        },
    }
    return card


def send_card(webhook_url, card):
    try:
        r = s.post(webhook_url, json=card, timeout=15)
        result = r.json()
        ok = result.get("code") == 0 or result.get("StatusCode") == 0
        print(f"{'✅' if ok else '❌'} 飞书推送{'成功' if ok else '失败: ' + str(result)}")
        return ok
    except Exception as e:
        print(f"❌ 推送异常: {e}")
        return False


def send_text(webhook_url, text):
    try:
        r = s.post(webhook_url, json={"msg_type": "text", "content": {"text": text}}, timeout=15)
        result = r.json()
        return result.get("code") == 0
    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"   推送文本消息异常: {e}")
        return False


# ========== 主流程 ==========
def main():
    print("=" * 50)
    print("  A股日报生成 & 飞书推送")
    print("=" * 50)

    config = load_config()
    if not config or not config.get("webhook_url"):
        print("\n⚠️ 未配置飞书 Webhook！")
        print("运行: python daily_feishu_report.py --setup <URL>")
        return

    webhook_url = config["webhook_url"]
    today = time.strftime("%Y年%m月%d日 %A")

    # 1. 指数
    print("\n📡 [1/4] 大盘指数（腾讯）...")
    indices = fetch_indices()
    for idx in indices:
        sgn = "+" if idx["change_pct"] >= 0 else ""
        print(f"   {idx['name']}: {idx['price']:.2f} ({sgn}{idx['change_pct']:.2f}%)")

    if not indices:
        print("❌ 无法获取指数数据")
        return

    # 2. 成交额
    print("\n📡 [2/4] 成交额（腾讯）...")
    turnover = fetch_turnover_from_tencent()
    print(f"   两市成交额: {turnover:.0f} 亿")

    # 3. 涨停板
    print("\n📡 [3/4] 涨停板扫描（腾讯批量）...")
    t0 = time.time()
    zt_list = fetch_limit_up_tencent()
    elapsed = time.time() - t0
    print(f"   涨停: {len(zt_list)} 只 (耗时 {elapsed:.0f}s)")
    for z in sorted(zt_list, key=lambda x: x["change_pct"], reverse=True)[:10]:
        print(f"   {z['code']} {z['name']} +{z['change_pct']:.1f}%")

    # 4. 板块
    print("\n📡 [4/4] 热门板块（腾讯）...")
    sectors = fetch_sectors_tencent()
    print(f"   获取: {len(sectors)} 个板块")
    for s in sectors[:5]:
        sgn = "+" if s["change_pct"] >= 0 else ""
        print(f"   {s['name']} {sgn}{s['change_pct']:.2f}%")

    # 推送
    print("\n📤 推送到飞书...")
    card = build_feishu_card(indices, zt_list, sectors, turnover, today)
    ok = send_card(webhook_url, card)

    if not ok:
        # 降级文本
        text = f"A股日报 | {today}\n{'='*30}\n📈 大盘：\n"
        for idx in indices:
            sgn = "+" if idx["change_pct"] >= 0 else ""
            text += f"  {idx['name']}: {idx['price']:.2f} ({sgn}{idx['change_pct']:.2f}%)\n"
        text += f"\n💰 成交额: {turnover:.0f} 亿\n"
        if zt_list:
            text += f"\n🔥 涨停: {len(zt_list)}只\n"
            for z in sorted(zt_list, key=lambda x: x["change_pct"], reverse=True)[:15]:
                text += f"  {z['code']} {z['name']} +{z['change_pct']:.1f}%\n"
        text += "\n⚠️ 仅供参考"
        send_text(webhook_url, text)

    print(f"\n✅ 完成 {time.strftime('%H:%M:%S')}")


def setup():
    if len(sys.argv) > 2 and sys.argv[1] == "--setup":
        webhook = sys.argv[2]
        config = {"webhook_url": webhook, "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"✅ 已保存")

        test_card = {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": "✅ A股日报系统已就绪"}, "template": "green"},
                "elements": [{
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": "每晚 **20:00** 自动推送A股日报\n\n大盘指数 / 涨停板 / 热门板块 / 成交额"},
                }],
            },
        }
        send_card(webhook, test_card)
    else:
        print("用法: python daily_feishu_report.py --setup <webhook_url>")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--setup":
        setup()
    else:
        main()
