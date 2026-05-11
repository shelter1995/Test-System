"""
RAG 知识库客户端 — 封装 RAG-Anything API 交互，支持并行多查询
"""

import logging
import requests
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class RAGClient:
    """RAG 知识库 HTTP 客户端"""

    def __init__(self, base_url: str = "http://localhost:8003", timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    def list_databases(self) -> List[dict]:
        """GET /db/list → 数据库列表"""
        resp = self._session.get(f"{self.base_url}/db/list", timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data.get("databases", data if isinstance(data, list) else [])

    def get_db_stats(self, database: str) -> dict:
        """GET /db/stats/{database} → 数据库统计"""
        resp = self._session.get(f"{self.base_url}/db/stats/{database}", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def search(self, query: str, database: str, n_results: int = 10) -> List[dict]:
        """POST /search → 语义检索结果"""
        resp = self._session.post(
            f"{self.base_url}/search",
            json={"query": query, "n_results": n_results, "database": database, "enable_rerank": False},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])

    def ai_enhanced_search(self, query: str, database: str, n_results: int = 10) -> List[dict]:
        """POST /ai_enhanced_search → AI 增强检索结果"""
        resp = self._session.post(
            f"{self.base_url}/ai_enhanced_search",
            json={"query": query, "n_results": n_results, "database": database, "enable_rerank": False},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])

    def multi_query_search(
        self, queries: List[str], database: str, n_results: int = 10, use_enhanced: bool = True
    ) -> Dict[str, List[dict]]:
        """
        并行执行多个检索查询。

        Returns:
            {query_string: [result_dict, ...], ...}
        """
        results: Dict[str, List[dict]] = {}
        search_fn = self.ai_enhanced_search if use_enhanced else self.search

        with ThreadPoolExecutor(max_workers=min(len(queries), 5)) as executor:
            future_to_query = {executor.submit(search_fn, q, database, n_results): q for q in queries}
            for future in as_completed(future_to_query, timeout=180):
                query = future_to_query[future]
                try:
                    results[query] = future.result()
                except Exception as e:
                    logger.warning(f"RAG 检索失败 '{query}': {e}")
                    results[query] = []

        return results


# 单例
_rag_client: Optional[RAGClient] = None


def get_rag_client(base_url: str = None) -> RAGClient:
    global _rag_client
    if _rag_client is None:
        import tutor_config as config

        url = base_url or getattr(config, "RAG_SERVICE_URL", "http://localhost:8003")
        _rag_client = RAGClient(base_url=url)
    return _rag_client
