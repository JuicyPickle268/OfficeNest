"""
System Skill：文件管理 + 注册表管理等杂项工具。
"""
from pathlib import Path
from skills.base import BaseSkill


class SystemSkill(BaseSkill):

    def __init__(self, file_registry=None, zhihu_key: str = ""):
        self._registry = file_registry
        self._zhihu_key = zhihu_key

    @property
    def name(self) -> str:
        return "system"

    def get_tools(self) -> list[dict]:
        tools = [
            {"name": "file_list_dir", "fn": self.file_list_dir,
             "schema": self._schema("列出指定目录下的所有文件", {
                 "path": {"type": "string", "description": "目录路径，如 ./workbooks"},
             }, ["path"])},
            {"name": "file_delete", "fn": self.file_delete,
             "schema": self._schema("删除本地文件", {
                 "filepath": {"type": "string", "description": "要删除的文件路径"},
             }, ["filepath"])},
            {"name": "web_search", "fn": self.web_search,
             "schema": self._schema("通用网页搜索（DuckDuckGo+Bing聚合）——实时资讯、英文资料、国外信息", {
                 "query": {"type": "string", "description": "搜索关键词"},
                 "max_results": {"type": "integer", "description": "最大结果数，默认5"},
             }, ["query"])},
            {"name": "zhihu_search", "fn": self.zhihu_search,
             "schema": self._schema("知乎站内搜索——中文深度内容、行业分析、人物资料、知识问答", {
                 "query": {"type": "string", "description": "搜索关键词"},
                 "max_results": {"type": "integer", "description": "最大结果数，默认5"},
             }, ["query"])},
            {"name": "global_search", "fn": self.global_search,
             "schema": self._schema("全网搜索（知乎API）——实时资讯、综合网页、替代bing搜索", {
                 "query": {"type": "string", "description": "搜索关键词"},
                 "max_results": {"type": "integer", "description": "最大结果数，默认5"},
             }, ["query"])},
            {"name": "file_copy", "fn": self.file_copy,
             "schema": self._schema("复制文件到新位置", {
                 "src": {"type": "string", "description": "源文件路径"},
                 "dst": {"type": "string", "description": "目标路径"},
             }, ["src", "dst"])},
            {"name": "file_move", "fn": self.file_move,
             "schema": self._schema("移动或重命名文件", {
                 "src": {"type": "string", "description": "源文件路径"},
                 "dst": {"type": "string", "description": "目标路径"},
             }, ["src", "dst"])},
            {"name": "file_open", "fn": self.file_open,
             "schema": self._schema("用系统默认程序打开文件（Excel/Word/PDF等）", {
                 "filepath": {"type": "string", "description": "文件路径"},
             }, ["filepath"])},
            {"name": "file_search", "fn": self.file_search,
             "schema": self._schema("全盘秒搜文件——比 file_list_dir 快，可搜任意目录", {
                 "query": {"type": "string", "description": "文件名关键词或通配符，如 *.xlsx 或 招聘"},
             }, ["query"])},
        ]
        if self._registry:
            tools.append(
                {"name": "file_deregister", "fn": self.file_deregister,
                 "schema": self._schema("从文件注册表中移除某个文件（不删除实际文件）", {
                     "name": {"type": "string", "description": "文件名，如 招聘数据表.xlsx"},
                 }, ["name"])}
            )
        return tools

    def file_list_dir(self, path: str = "./workbooks") -> str:
        from adapters.file_bridge import FileBridge
        fb = FileBridge()
        files = fb.list_dir(path, "*")
        if not files:
            return f"（{path} 目录为空或不存在）"
        lines = [f"{path}/"]
        for f in sorted(files):
            suffix = "/" if f.is_dir() else ""
            size = f.stat().st_size if f.is_file() else 0
            kb = f" ({size/1024:.1f}KB)" if size > 1024 else ""
            lines.append(f"  {f.name}{suffix}{kb}")
        return "\n".join(lines)

    def web_search(self, query: str, max_results: int = 5) -> str:
        """通用搜索引擎聚合（DuckDuckGo + Bing）。"""
        from adapters.search_agent import get_agent
        try:
            return get_agent().search(query, max_results)
        except Exception:
            return f"（搜索'{query}'无结果）"

    def zhihu_search(self, query: str, max_results: int = 5) -> str:
        """知乎站内搜索（需要 zhihu_api_key）。"""
        if not self._zhihu_key:
            return "❌ 知乎搜索需要 API Key，请在设置中填写 zhihu_api_key"
        import httpx, time
        try:
            resp = httpx.get(
                "https://developer.zhihu.com/api/v1/content/zhihu_search",
                params={"Query": query, "Count": min(max_results, 10)},
                headers={
                    "Authorization": f"Bearer {self._zhihu_key}",
                    "X-Request-Timestamp": str(int(time.time())),
                },
                timeout=8,
            )
            data = resp.json()
            if data.get("Code") != 0:
                return f"知乎搜索失败: {data.get('Message', '未知错误')}"
            items = data["Data"]["Items"]
            if not items:
                return f"（知乎未找到关于'{query}'的内容）"
            lines = []
            for i, it in enumerate(items[:max_results]):
                lines.append(f"{i+1}. {it['Title']}")
                lines.append(f"   {it['ContentText'][:150]}")
                lines.append(f"   👍{it['VoteupCount']} | {it['Url']}")
            return "\n".join(lines)
        except Exception as e:
            return f"知乎搜索失败: {e}"

    def global_search(self, query: str, max_results: int = 5) -> str:
        """知乎全网搜索 API——替代 Bing，覆盖全中文网络。"""
        if not self._zhihu_key:
            return "❌ 全网搜索需要知乎 API Key"
        import httpx, time
        try:
            resp = httpx.get(
                "https://developer.zhihu.com/api/v1/content/global_search",
                params={"Query": query, "Count": min(max_results, 10)},
                headers={
                    "Authorization": f"Bearer {self._zhihu_key}",
                    "X-Request-Timestamp": str(int(time.time())),
                },
                timeout=8,
            )
            data = resp.json()
            if data.get("Code") != 0:
                return f"全网搜索失败: {data.get('Message', '')}"
            items = data["Data"]["Items"]
            if not items:
                return f"（未找到关于'{query}'的结果）"
            lines = []
            for i, it in enumerate(items[:max_results]):
                lines.append(f"{i+1}. {it['Title']}")
                lines.append(f"   {it['ContentText'][:150]}")
                lines.append(f"   👍{it.get('VoteUpCount',0)} | {it['Url']}")
            return "\n".join(lines)
        except Exception as e:
            return f"全网搜索失败: {e}"

    def file_delete(self, filepath: str) -> str:
        path = Path(filepath)
        if not path.is_absolute():
            path = Path("./workbooks") / path.name
        if not path.exists():
            return f"❌ 文件不存在: {path.name}"
        try:
            path.unlink()
            return f"✅ 已删除: {path.name}"
        except Exception as e:
            return f"❌ 删除失败: {e}"

    def file_copy(self, src: str, dst: str) -> str:
        """复制文件。"""
        from adapters.file_bridge import FileBridge
        fb = FileBridge()
        if not fb.exists(src):
            return f"❌ 源文件不存在: {src}"
        try:
            fb.copy_file(src, dst)
            return f"✅ 已复制: {Path(src).name} → {dst}"
        except Exception as e:
            return f"❌ 复制失败: {e}"

    def file_move(self, src: str, dst: str) -> str:
        """移动/重命名文件。"""
        from adapters.file_bridge import FileBridge
        fb = FileBridge()
        if not fb.exists(src):
            return f"❌ 源文件不存在: {src}"
        try:
            fb.move_file(src, dst)
            return f"✅ 已移动: {Path(src).name} → {dst}"
        except Exception as e:
            return f"❌ 移动失败: {e}"

    def file_open(self, filepath: str) -> str:
        """用系统默认程序打开文件。"""
        import subprocess, platform
        path = Path(filepath)
        if not path.exists():
            return f"❌ 文件不存在: {filepath}"
        try:
            if platform.system() == "Windows":
                subprocess.Popen(["start", str(path)], shell=True)
            else:
                subprocess.Popen(["xdg-open", str(path)])
            return f"✅ 已打开: {path.name}"
        except Exception as e:
            return f"❌ 打开失败: {e}"

    def file_search(self, query: str) -> str:
        """全盘秒搜文件（优先 Everything，回退 glob）。"""
        # 尝试 es.exe
        import subprocess, shutil
        es = shutil.which("es.exe") or shutil.which("es")
        if es:
            try:
                r = subprocess.run([es, "-n", "30", query], capture_output=True, text=True, timeout=5)
                if r.stdout.strip():
                    files = r.stdout.strip().split("\n")[:20]
                    return f"搜索'{query}':\n" + "\n".join(f"  {f}" for f in files)
            except Exception:
                pass
        # Fallback: glob 本地目录
        from pathlib import Path as P
        import glob
        results = []
        for d in ["./workbooks", "./output", "./templates", "."]:
            for p in P(d).rglob(query if "*" in query else f"*{query}*"):
                if p.is_file():
                    results.append(str(p))
        if results:
            return f"搜索'{query}' (本地):\n" + "\n".join(f"  {r}" for r in results[:20])
        return f"（未找到匹配'{query}'的文件。可安装 Everything 工具实现全盘搜索）"

    def file_deregister(self, name: str) -> str:
        if not self._registry:
            return "❌ 注册表不可用"
        if self._registry.unregister(name):
            return f"✅ 已从注册表移除: {name}"
        return f"❌ 注册表中未找到: {name}"

    @staticmethod
    def _schema(desc: str, properties: dict, required: list[str] | None = None) -> dict:
        return {"type": "function", "function": {
            "description": desc,
            "parameters": {"type": "object", "properties": properties, "required": required or []}
        }}
