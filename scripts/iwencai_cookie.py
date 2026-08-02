"""
iwencai 统一模块 — 基于 pywencai + hexin-v cookie 认证。
无需 IWENCAI_API_KEY，无需登录 skillhub，自动生成 hexin-v token。

参考: auto_iwencai.py (F:\备份-2026-06-11\Python\iwencai_project)

核心策略（参考 auto_iwencai.py 的经验）：
- pywencai 内部 monkey-patch 不可靠（模块导入时引用已固化）
- 改为直接发送 HTTP 请求（requests Session），绕过 pywencai.get()
- 仅复用 pywencai 的 get_token() 生成 hexin-v，以及 convert.py 解析响应
- 请求完成后结果转为 pandas DataFrame

Token 获取三方案（按优先级降级）:
    1) pywencai.get_token() — 主用，最简洁
    2) fetch_hexin_v.js (Node.js 直调) — 备用，pywencai Python 层坏了也能跑
    3) 手动设置 — 最后兜底: iwc.set_token("your-hexin-v")

用法:
    from scripts.iwencai_cookie import get_iwencai
    iwc = get_iwencai()
    df = iwc.search("人形机器人 丝杠 减速器")
    df = iwc.search_report("人形机器人 产业链")  # 研报
    df = iwc.search_announcement("减持")          # 公告
    df = iwc.search_news("产业链")                # 新闻

    # 手动设置 token（兜底方案）
    iwc.set_token("your-hexin-v-token")
"""

import os
import json
import subprocess
import logging
from typing import Optional

import pandas as pd
import requests
import pydash as _

logger = logging.getLogger(__name__)


# ---- 防封：去掉代理（参考 auto_iwencai.py 第 21-23 行）----
for k in list(os.environ.keys()):
    if k.upper() in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(k, None)


# ========================
# Token 获取方案
# ========================

def _gen_hexin_v_pywencai() -> Optional[str]:
    """方案一（主用）：调用 pywencai 内置 get_token() 生成 hexin-v token。"""
    try:
        import pywencai.headers as ph
        token = ph.get_token()
        if token and len(token) > 10:
            logger.debug("token 获取: pywencai (主用)")
            return token
        logger.warning("pywencai get_token() 返回的 token 无效: %s", (token[:8] + "****") if token else "None")
    except Exception as e:
        logger.warning("pywencai get_token() 失败: %s", e)
    return None


def _gen_hexin_v_nodejs() -> Optional[str]:
    """方案二（备用）：Node.js 直调 fetch_hexin_v.js。
    绕过 pywencai Python 封装层，直接通过 Node.js subprocess 运行 hexin-v.bundle.js。
    适用于 pywencai 库 import 失败或 API 变更不可用的情况。
    """
    try:
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fetch_hexin_v.js')
        if not os.path.exists(script):
            logger.warning("fetch_hexin_v.js 不存在: %s", script)
            return None

        result = subprocess.run(
            ['node', script],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(script),
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )

        if result.stderr:
            logger.debug("Node.js stderr: %s", result.stderr.strip())

        data = json.loads(result.stdout.strip())
        if data.get('success'):
            token = data.get('hexin_v', '')
            if token and len(token) > 10:
                logger.debug("token 获取: Node.js fetch_hexin_v.js (备用)")
                return token
            logger.warning("Node.js 返回的 token 无效: %s", (token[:8] + "****") if token else "None")
        else:
            logger.warning("Node.js fetch_hexin_v.js 失败: %s", data.get('error', 'unknown'))
    except subprocess.TimeoutExpired:
        logger.warning("Node.js fetch_hexin_v.js 超时 (>30s)")
    except FileNotFoundError:
        logger.warning("Node.js 未安装，无法使用备用方案")
    except json.JSONDecodeError as e:
        logger.warning("Node.js 输出 JSON 解析失败: %s", e)
    except Exception as e:
        logger.warning("Node.js fetch_hexin_v.js 异常: %s", e)
    return None


def _parse_url_params(url):
    """解析 URL query 参数为 dict。复用 pywencai.convert.parse_url_params 逻辑。"""
    if not url:
        return {}
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    for k, v in params.items():
        if isinstance(v, list) and len(v) == 1:
            params[k] = v[0]
    return params


def _convert_robot_data(result: dict) -> dict:
    """将 get-robot-data 响应转为 {data, url, url_params}。
    等价于 pywencai.convert.convert() 但直接用 dict 参数而非 Response 对象。
    """
    content = _.get(result, 'data.answer.0.txt.0.content')
    if isinstance(content, str):
        content = json.loads(content)

    components = content.get('components', [])

    if (len(components) == 1 and
            _.get(components[0], 'show_type') == 'xuangu_tableV1'):
        comp = components[0]
        return {
            'data': {
                'condition': _.get(comp, 'data.meta.extra.condition'),
                'comp_id': comp.get('cid'),
                'uuid': comp.get('puuid'),
            },
            'row_count': _.get(comp, 'data.meta.extra.row_count'),
            'url': _.get(comp, 'config.other_info.footer_info.url'),
            'url_params': _parse_url_params(
                _.get(comp, 'config.other_info.footer_info.url', '')
            ),
        }
    else:
        # 多组件结果
        url = _.get(components[0], 'config.other_info.footer_info.url', '')
        # 收集每个组件的数据
        result_data = {}
        for comp in components:
            key = (_.get(comp, 'title_config.data.h1') or
                   _.get(comp, 'config.title') or
                   comp.get('show_type'))
            show_type = comp.get('show_type')
            if show_type in ('txt1', 'txt2'):
                result_data[key] = _.get(comp, 'data.content', '')
            elif show_type == 'xuangu_tableV1':
                result_data[key] = {
                    'condition': _.get(comp, 'data.meta.extra.condition'),
                    'comp_id': comp.get('cid'),
                    'uuid': comp.get('puuid'),
                }
            else:
                # common_handler: datas 或 data
                datas = _.get(comp, 'data.datas')
                if isinstance(datas, list) and datas:
                    result_data[key] = pd.DataFrame.from_dict(datas)
                else:
                    result_data[key] = _.get(comp, 'data', {})
        return {
            'data': result_data,
            'url': url,
            'url_params': _parse_url_params(url),
        }


def _query_robot_data(token: str, query: str,
                      page: int = 1, perpage: int = 100,
                      query_type: str = 'stock') -> tuple:
    """直接 HTTP 调用 get-robot-data，返回 (转后的 data dict, 总行数)。"""
    s = requests.Session()
    s.trust_env = False

    hexin_v = f'hexin-v={token}'
    headers = {
        'hexin-v': token,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'cookie': hexin_v,
        'Referer': 'https://www.iwencai.com/screener',
        'Content-Type': 'application/json',
    }

    data = {
        'question': query,
        'perpage': str(perpage),
        'page': str(page),
        'secondary_intent': query_type,
        'log_info': '{"input_type":"typewrite"}',
        'source': 'Ths_iwencai_Xuangu',
        'version': '2.0',
    }

    r = s.post(
        'https://www.iwencai.com/customized/chart/get-robot-data',
        json=data,
        headers=headers,
        timeout=15,
    )

    if r.status_code != 200:
        raise RuntimeError(f"iwencai 返回 HTTP {r.status_code}")

    result = json.loads(r.text)
    params = _convert_robot_data(result)
    row_count = params.get('row_count', 0) or 0
    return params, row_count


def _fetch_data_page(token: str, url_params: dict,
                     page: int = 1, perpage: int = 100,
                     condition: dict = None) -> pd.DataFrame:
    """调用分页接口获取股票列表数据。"""
    s = requests.Session()
    s.trust_env = False

    hexin_v = f'hexin-v={token}'
    req_headers = {
        'hexin-v': token,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'cookie': hexin_v,
        'Referer': 'https://www.iwencai.com/screener',
        'Content-Type': 'application/x-www-form-urlencoded',
    }

    post_data = {
        **url_params,
        'perpage': str(perpage),
        'page': str(page),
    }
    if condition:
        post_data['condition'] = condition

    r = s.post(
        'https://www.iwencai.com/gateway/urp/v7/landing/getDataList',
        data=post_data,
        headers=req_headers,
        timeout=(5, 15),
    )

    try:
        result = json.loads(r.text)
    except json.JSONDecodeError:
        return pd.DataFrame()

    datas = _.get(result, 'answer.components.0.data.datas', [])
    if not datas:
        return pd.DataFrame()
    return pd.DataFrame.from_dict(datas)


class IwencaiClient:
    """基于 pywencai get_token() + 直连 HTTP 的 iwencai 客户端。

    优势：
    - 无需 IWENCAI_API_KEY（不用登录 skillhub）
    - 直连 iwencai.com，绕过 pywencai 的 monkey-patch 限制
    - 完全控制请求头，防 403 防封 IP
    - 双方案 token 获取（pywencai 主 + Node.js 备），外加手动兜底

    Token 获取优先级:
    1. 手动设置 (set_token) — 最高优先级
    2. pywencai.get_token() — 主用，自动通过 Node.js 运行 hexin-v.bundle.js
    3. fetch_hexin_v.js 直调 — 备用，绕过 Python 封装层
    """

    def __init__(self):
        self._token = None
        self._token_source = None  # 'manual' | 'pywencai' | 'nodejs' | None

    @property
    def token(self) -> str:
        if self._token is None:
            # 手动设置过的 token 优先保留
            if self._token_source == 'manual':
                return self._token
            # 自动获取: 方案一（主用 pywencai）
            self._token = _gen_hexin_v_pywencai()
            if self._token:
                self._token_source = 'pywencai'
            else:
                # 自动获取: 方案二（备用 Node.js）
                self._token = _gen_hexin_v_nodejs()
                if self._token:
                    self._token_source = 'nodejs'
        if self._token is None:
            raise RuntimeError(
                "所有自动获取 token 方式均失败。\n"
                "  请手动设置: iwc.set_token('your-hexin-v-token')\n"
                "  或检查: pywencai 安装 + Node.js 安装"
            )
        return self._token

    @property
    def token_source(self) -> Optional[str]:
        """返回当前 token 的来源: 'manual' | 'pywencai' | 'nodejs' | None"""
        return self._token_source

    def set_token(self, token: str):
        """手动设置 hexin-v token（兜底方案）。

        适用于所有自动获取方式都失败时，手动从浏览器 DevTools 复制 cookie。
        设置后 refresh_token() 会清除手动设置的 token 并重新走自动流程。
        """
        self._token = token
        self._token_source = 'manual'
        logger.info("token: manual (手动设置)")

    def refresh_token(self, force_auto: bool = True):
        """刷新 token。

        Args:
            force_auto: True=清除后强制自动获取, False=只清除缓存下次查时自动获取
        """
        self._token = None
        self._token_source = None
        if force_auto:
            return self.token
        return None

    def search(self, query: str, loop: bool = False, **kwargs) -> pd.DataFrame:
        """通用语义搜索（问财 AI 选股语法），返回 DataFrame。

        Args:
            query: 问财查询语句
            loop: 是否分页获取全部结果（默认只取第一页 100 条）
        """
        page = kwargs.pop('page', 1)
        perpage = kwargs.pop('perpage', 100)
        query_type = kwargs.pop('query_type', 'stock')

        try:
            params, row_count = _query_robot_data(
                self.token, query, page=page, perpage=min(perpage, 100),
                query_type=query_type
            )
        except RuntimeError as e:
            print(f"[iwencai] search '{query[:30]}...' 失败: {e}")
            return pd.DataFrame()

        data = params.get('data', {})
        url_params = params.get('url_params', {})

        # 提取 condition（xuangu_tableV1 类型）
        condition = None
        if isinstance(data, dict):
            condition = data.get('condition')

        if condition:
            # 有 condition 说明是选股类型，调用分页接口
            if loop and row_count > 0:
                max_page = (row_count + perpage - 1) // perpage
                max_page = min(max_page, 10)  # 最多取 10 页
                frames = []
                for p in range(page, page + max_page):
                    df = _fetch_data_page(
                        self.token, url_params, page=p,
                        perpage=perpage, condition=condition
                    )
                    if df.empty:
                        break
                    frames.append(df)
                if frames:
                    return pd.concat(frames, ignore_index=True)
                return pd.DataFrame()
            else:
                return _fetch_data_page(
                    self.token, url_params, page=page,
                    perpage=perpage, condition=condition
                )
        else:
            # 非选股类型（纯文本/研报/公告等），返回 data 中的 DataFrame
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, pd.DataFrame) and not v.empty:
                        return v
                # 没有 DataFrame，返回文本数据
                return pd.DataFrame([data])
            return pd.DataFrame()

    def search_report(self, keywords: str, limit: int = 20) -> pd.DataFrame:
        """研报检索。"""
        query = f"{keywords}"
        df = self.search(query)
        return df.head(limit) if not df.empty else df

    def search_announcement(self, keywords: str, limit: int = 20) -> pd.DataFrame:
        """公告检索。"""
        query = f"{keywords}"
        df = self.search(query)
        return df.head(limit) if not df.empty else df

    def search_news(self, keywords: str, limit: int = 20) -> pd.DataFrame:
        """新闻检索。"""
        query = f"{keywords}"
        df = self.search(query)
        return df.head(limit) if not df.empty else df


# ---- 单例 ----
_iwencai_instance = None


def get_iwencai() -> IwencaiClient:
    """获取 iwencai 客户端单例。"""
    global _iwencai_instance
    if _iwencai_instance is None:
        _iwencai_instance = IwencaiClient()
    return _iwencai_instance


# ---- 命令行入口 ----
if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 60)
    print("   iwencai 直连模块测试 (双方案 token)")
    print("=" * 60)

    iwc = get_iwencai()
    print(f"\n[Token] 来源: {iwc.token_source}")
    print(f"         值: {iwc.token[:8]}****... (len={len(iwc.token)})")

    # 测试 1: 选股
    print("\n[测试1] 人形机器人 丝杠 减速器")
    df = iwc.search("人形机器人 丝杠 减速器")
    if not df.empty:
        print(f"  结果: {len(df)} 行 × {len(df.columns)} 列")
        show_cols = [c for c in df.columns
                     if any(k in c for k in ['简称', '代码', '股价', '涨跌幅', 'PE',
                                             'name', 'code', 'price', 'change', 'pe'])
                     ][:8]
        if not show_cols:
            show_cols = list(df.columns)[:6]
        print(f"  列: {show_cols}")
        print(df[show_cols].head(8).to_string(index=False))
    else:
        print("  无结果")

    # 测试 2: 研报
    print("\n[测试2] 绿的谐波 研报")
    df = iwc.search_report("绿的谐波 研报")
    if not df.empty:
        print(f"  结果: {len(df)} 行")
        print(f"  列: {list(df.columns)[:10]}")
    else:
        print("  无结果")

    # 测试 3: 公告
    print("\n[测试3] 减持公告")
    df = iwc.search_announcement("减持")
    if not df.empty:
        print(f"  结果: {len(df)} 行")
    else:
        print("  无结果")
