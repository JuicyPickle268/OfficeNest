"""
轻量搜索代理——聚合多个搜索源，纯 Python，无需 Docker。
自动端口探测，退出时自清理。
"""
import json
import time
import socket
import threading
import httpx


def _find_free_port(start: int = 8081) -> int:
    """找到空闲端口。"""
    port = start
    while port < 8100:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
        port += 1
    raise RuntimeError("无可用端口 (8081-8099)")


def _search_duckduckgo(query: str, timeout: float = 8) -> list[dict]:
    """DuckDuckGo Instant Answer API。"""
    try:
        resp = httpx.get(
            "https://api.duckduckgo.com",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=timeout,
        )
        data = resp.json()
        results = []
        for r in data.get("RelatedTopics", [])[:5]:
            if "Text" in r:
                results.append({"title": "", "body": r["Text"][:200],
                                "url": r.get("FirstURL", "")})
        if data.get("AbstractText"):
            results.insert(0, {"title": data.get("AbstractSource", ""),
                                "body": data["AbstractText"][:300],
                                "url": data.get("AbstractURL", "")})
        return results
    except Exception:
        return []


def _search_bing(query: str, timeout: float = 8) -> list[dict]:
    """Bing 搜索（国内版）。"""
    import re
    try:
        resp = httpx.get(
            "https://cn.bing.com/search",
            params={"q": query, "count": 5},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
            timeout=timeout,
        )
        results = re.findall(
            r'<li class="b_algo"[^>]*>.*?<h2[^>]*><a[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?<p[^>]*>(.*?)</p>',
            resp.text, re.DOTALL,
        )
        out = []
        for url, title, desc in results[:5]:
            title_clean = re.sub(r'<[^>]+>', '', title).strip()
            desc_clean = re.sub(r'<[^>]+>', '', desc).strip()
            out.append({"title": title_clean, "body": desc_clean[:200], "url": url})
        return out
    except Exception:
        return []


class SearchAgent:
    """搜索代理——多源聚合+去重，自动端口探测。"""

    def __init__(self, port: int | None = None):
        self._port = port or _find_free_port()
        self._running = False
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._port

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}/search"

    def start(self):
        """启动轻量 HTTP 搜索服务。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        time.sleep(0.3)

    def stop(self):
        """停止服务。"""
        self._running = False

    def search(self, query: str, max_results: int = 5) -> str:
        """执行搜索——聚合 DuckDuckGo + Bing。"""
        results = []
        # 并行搜索
        ddg = _search_duckduckgo(query)
        bing = _search_bing(query)
        seen = set()
        for r in ddg + bing:
            key = r.get("url", "") or r.get("body", "")[:50]
            if key and key not in seen:
                seen.add(key)
                results.append(r)

        if not results:
            return f"（未找到关于'{query}'的结果）"

        lines = []
        for i, r in enumerate(results[:max_results]):
            lines.append(f"{i+1}. {r.get('title', '')}")
            if r.get("body"):
                lines.append(f"   {r['body'][:150]}")
            if r.get("url"):
                lines.append(f"   {r['url']}")
        return "\n".join(lines)

    def _serve(self):
        """简易 HTTP 服务——接收搜索请求。"""
        import http.server

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                from urllib.parse import urlparse, parse_qs
                q = urlparse(self.path)
                if q.path == "/search":
                    params = parse_qs(q.query)
                    query = params.get("q", [""])[0]
                    result = {"query": query, "results": []}
                    ddg = _search_duckduckgo(query)
                    bing = _search_bing(query)
                    seen = set()
                    for r in ddg + bing:
                        key = r.get("url", "") or r.get("body", "")[:50]
                        if key and key not in seen:
                            seen.add(key)
                            result["results"].append(r)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps(result, ensure_ascii=False).encode())
                else:
                    self.send_response(404)
                    self.end_headers()

        server = http.server.HTTPServer(("127.0.0.1", self._port), Handler)
        server.timeout = 1
        while self._running:
            server.handle_request()


# 全局单例
_search_agent: SearchAgent | None = None


def get_agent() -> SearchAgent:
    global _search_agent
    if not _search_agent:
        _search_agent = SearchAgent()
        _search_agent.start()
    return _search_agent


def shutdown_agent():
    global _search_agent
    if _search_agent:
        _search_agent.stop()
        _search_agent = None
