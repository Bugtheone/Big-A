"""
iwencai OpenAPI 客户端（需要 API Key，更可靠、结构更丰富）

前置条件：
  - 登录 https://www.iwencai.com/skillhub 获取 API Key
  - 设置环境变量 IWENCAI_API_KEY 和 IWENCAI_BASE_URL
  - 安装对应技能（announcement-search / report-search / news-search）

使用方式：
  from scripts.iwencai_openapi import get_openapi
  api = get_openapi()
  results = api.search_announcement("减持公告")  → list of dict
  results = api.search_report("人形机器人")      → list of dict
  results = api.search_news("产业链")             → list of dict
"""
from __future__ import annotations

import os, json, uuid, logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

# config 路径（相对于项目根）
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.path.join(_BASE_DIR, "config", "iwencai_config.json")

SKILL_MAP = {
    "announcement": "announcement-search",
    "report":       "report-search",
    "news":         "news-search",
}


class IwencaiOpenAPI:
    """问财 OpenAPI 客户端 — 官方 API Key 认证，三个搜索频道"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        # 优先级：参数 > 环境变量 > config 文件
        self.api_key = api_key or os.environ.get("IWENCAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("IWENCAI_BASE_URL", "")
                         or "https://openapi.iwencai.com")

        if not self.api_key:
            self._load_from_config()

        self._session = requests.Session()
        self._session.trust_env = False

        if not self.api_key:
            logger.warning("IWENCAI_API_KEY 未设置，OpenAPI 不可用")
        else:
            logger.info(f"OpenAPI 已就绪 (key: {self.api_key[:6]}****...)")

    def _load_from_config(self):
        """从 config/iwencai_config.json 加载凭据（兜底方案）"""
        try:
            if os.path.exists(_CONFIG_PATH):
                with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.api_key = (self.api_key
                                or cfg.get("IWENCAI_API_KEY", "")
                                or cfg.get("api_key", ""))
                if not self.base_url or self.base_url == "https://openapi.iwencai.com":
                    self.base_url = cfg.get("base_url", self.base_url)
        except Exception as e:
            logger.debug(f"加载 iwencai config 失败: {e}")

    # ── 健康检查 ──────────────────────────────────────────

    def health_check(self, auto_refresh: bool = True) -> bool:
        """检查 API Key 是否有效。True=正常, False=已失效。

        调用任意频道返回结果即认为 Key 有效，遇到 401/403 即为过期。
        当 auto_refresh=True 且 Key 失效时，自动尝试从 skillhub 刷新。
        """
        if not self.api_key:
            logger.warning("API Key 未配置")
            if auto_refresh:
                return self._try_auto_refresh()
            return False

        try:
            headers = self._build_headers("announcement-search")
            r = self._session.post(
                f"{self.base_url}/v1/comprehensive/search",
                json={"query": "test", "channels": ["announcement"],
                      "app_id": "AIME_SKILL", "size": 1},
                headers=headers,
                timeout=15,
            )
            if r.status_code == 401:
                logger.warning("API Key 已过期或被撤销 (HTTP 401)")
                if auto_refresh:
                    return self._try_auto_refresh()
                return False
            if r.status_code == 403:
                logger.warning("API Key 无权限 (HTTP 403)")
                return False
            if r.status_code == 200:
                data = r.json()
                if data.get("status_code") == 0:
                    logger.info("API Key 有效 ✓")
                    return True
                status = data.get("status_code")
                msg = data.get("status_msg", "")
                logger.warning(f"API Key 可能失效: status_code={status}, msg={msg}")
                if auto_refresh and status != 0:
                    return self._try_auto_refresh()
                return status == 0
            logger.warning(f"健康检查失败: HTTP {r.status_code}")
            return False
        except requests.RequestException as e:
            logger.warning(f"健康检查网络异常: {e}")
            return False

    def _try_auto_refresh(self) -> bool:
        """尝试自动刷新 API Key（先无头，失败则启动浏览器）。"""
        logger.info("尝试自动刷新 API Key……")
        try:
            from scripts.iwencai_refresh_key import auto_refresh_or_raise
        except ImportError:
            logger.warning("自动刷新模块不可用，请手动刷新")
            return False

        auto_refresh_or_raise()

        # 无论上面的返回值如何，都尝试重新加载（Key 可能已写入 config 文件）
        self.api_key = ""
        self._load_from_config()
        self._load_from_env()
        if self.api_key:
            logger.info("API Key 自动刷新成功")
            return True

        logger.warning("自动刷新失败，请手动登录 skillhub 获取新 Key")
        return False

    def _load_from_env(self):
        """重新从环境变量加载 Key。"""
        self.api_key = self.api_key or os.environ.get("IWENCAI_API_KEY", "")

    # ── 公开接口 ──────────────────────────────────────────

    def query2data(
        self,
        query: str,
        page: str = "1",
        limit: str = "10",
        expand_index: bool = True,
    ) -> dict:
        """问财自然语言查询（选股/行情/财务/板块等核心能力）。

        Args:
            query: 自然语言查询，如 "ROE>20%且PE<30的消费股"
            page: 页码（字符串），默认 "1"
            limit: 每页条数（字符串），默认 "10"
            expand_index: 是否扩展指数查询结果，默认 True

        Returns:
            dict: {
                success: bool,
                code_count: int,       # 命中数量
                data: list,            # 结果行（含 code/name/最新价等）
                raw: dict,             # 原始响应
                message: str,
            }
        """
        if not self.api_key:
            raise RuntimeError("IWENCAI_API_KEY 未设置，无法调用 OpenAPI")

        payload = {
            "query": query,
            "page": str(page),
            "limit": str(limit),
            "is_cache": "1",
            "expand_index": "true" if expand_index else "false",
        }
        headers = self._build_headers("astock-selector")

        try:
            r = self._session.post(
                f"{self.base_url}/v1/query2data",
                json=payload,
                headers=headers,
                timeout=30,
            )
            if r.status_code == 401:
                logger.warning("API Key 已过期或被撤销！请调用 iwencai_key_refresh() 刷新")
                return {"success": False, "code_count": 0, "data": [],
                        "raw": {}, "message": "API Key 已过期"}
            if r.status_code != 200:
                logger.warning(f"query2data HTTP {r.status_code}: {r.text[:300]}")
                return {"success": False, "code_count": 0, "data": [],
                        "raw": {}, "message": f"HTTP {r.status_code}"}

            data = r.json()
            # 兼容不同返回结构
            if isinstance(data, dict) and data.get("status_code") not in (None, 0):
                logger.warning(f"query2data status_code={data.get('status_code')}: {data.get('status_msg','')}")
                return {"success": False, "code_count": 0, "data": [],
                        "raw": data, "message": data.get("status_msg", "查询失败")}

            rows = []
            if isinstance(data, dict):
                rows = data.get("datas", data.get("data", []))
                if isinstance(rows, dict):
                    rows = rows.get("datas", [])
                count = data.get("code_count", 0) or len(rows)
            elif isinstance(data, list):
                rows = data
                count = len(data)
            else:
                count = 0

            return {
                "success": True,
                "code_count": count,
                "data": rows,
                "raw": data,
                "message": f"命中 {count} 条",
            }
        except requests.RequestException as e:
            logger.warning(f"query2data 请求异常: {e}")
            return {"success": False, "code_count": 0, "data": [],
                    "raw": {}, "message": f"网络异常: {e}"}

    def search_announcement(self, query: str, size: int = 10) -> list[dict]:
        """搜索公告（减持、分红、回购、重组等）"""
        return self._search("announcement", query, size)

    def search_report(self, query: str, size: int = 10) -> list[dict]:
        """搜索研报（行业/公司/策略研报）"""
        return self._search("report", query, size)

    def search_news(self, query: str, size: int = 10) -> list[dict]:
        """搜索新闻（财经资讯/快讯/深度报道）"""
        return self._search("news", query, size)

    # ── 内部实现 ──────────────────────────────────────────

    def _search(self, channel: str, query: str, size: int = 10) -> list[dict]:
        if not self.api_key:
            raise RuntimeError("IWENCAI_API_KEY 未设置，无法调用 OpenAPI")

        skill_id = SKILL_MAP[channel]
        headers = self._build_headers(skill_id)
        payload = {
            "query": query,
            "channels": [channel],
            "app_id": "AIME_SKILL",
            "size": size,
        }

        try:
            r = self._session.post(
                f"{self.base_url}/v1/comprehensive/search",
                json=payload,
                headers=headers,
                timeout=30,
            )
            if r.status_code != 200:
                if r.status_code == 401:
                    logger.warning("API Key 已过期或被撤销！请重新从 skillhub 获取")
                logger.warning(f"OpenAPI {channel} HTTP {r.status_code}: {r.text[:200]}")
                return []
            data = r.json()
            if data.get("status_code") != 0:
                logger.warning(f"OpenAPI {channel} status_code={data.get('status_code')}")
                return []
            return data.get("data", [])
        except requests.RequestException as e:
            logger.warning(f"OpenAPI {channel} 请求异常: {e}")
            return []

    def _build_headers(self, skill_id: str) -> dict:
        trace_id = uuid.uuid4().hex.upper()
        return {
            "Authorization": f"Bearer {self.api_key}",
            "X-Claw": self.api_key,
            "X-Claw-Call-Type": "normal",
            "X-Claw-Skill-Id": skill_id,
            "X-Claw-Skill-Version": "1.0.0",
            "X-Claw-Plugin-Id": "none",
            "X-Claw-Plugin-Version": "none",
            "X-Claw-Trace-Id": trace_id,
            "Content-Type": "application/json",
        }


# ── 单例 ──────────────────────────────────────────────────

_openapi_instance: Optional[IwencaiOpenAPI] = None


def get_openapi() -> IwencaiOpenAPI:
    """获取问财 OpenAPI 单例（需要有效的 IWENCAI_API_KEY）"""
    global _openapi_instance
    if _openapi_instance is None:
        _openapi_instance = IwencaiOpenAPI()
    return _openapi_instance


# ── 快速测试 ──────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    api = get_openapi()

    if not api.api_key:
        print("请先设置 IWENCAI_API_KEY 环境变量")
        exit(1)

    print(f"API Key:  {api.api_key[:25]}...")
    print(f"Base URL: {api.base_url}")
    print()

    # 健康检查
    status = "OK" if api.health_check() else "FAILED"
    print(f"[健康检查] {status}")
    print()

    for name, fn in [
        ("公告", api.search_announcement),
        ("研报", api.search_report),
        ("新闻", api.search_news),
    ]:
        results = fn("人形机器人 丝杠", size=3)
        print(f"[{name}] {len(results)} 条")
        if results:
            item = results[0]
            title = item.get("title", item.get("name", "N/A"))
            print(f"  → {title[:80]}")
        print()
