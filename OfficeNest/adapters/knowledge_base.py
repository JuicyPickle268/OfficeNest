"""
知识库——ChromaDB 向量存储 + SQLite 注册表。
支持本地嵌入（默认）和 DeepSeek Embedding API。
"""
import sqlite3, uuid, json
from pathlib import Path
from datetime import datetime, timezone


class KnowledgeBase:
    """本地向量知识库。"""

    def __init__(self, db_path: str = "./data/mother.db", persist_dir: str = "./data/kb",
                 use_deepseek_embed: bool = False, ds_api_key: str = ""):
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS kb_docs (
            id TEXT PRIMARY KEY, source TEXT, description TEXT,
            chunks INTEGER, created_at REAL)""")
        self._conn.commit()

        import chromadb
        self._chroma = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._chroma.get_or_create_collection("office_kb")

        self._use_ds = use_deepseek_embed
        self._ds_key = ds_api_key

    def add(self, text: str, source: str = "", description: str = "") -> str:
        """分段入库。"""
        chunks = []
        for i in range(0, len(text), 450):
            chunk = text[i:i + 500].strip()
            if len(chunk) > 20:
                chunks.append(chunk)
        if not chunks:
            return "❌ 文本太短"

        doc_id = f"kb_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).timestamp()

        # 写入 ChromaDB
        if self._use_ds and self._ds_key:
            embeddings = self._deepseek_embed(chunks)
            self._collection.add(documents=chunks, ids=[f"{doc_id}_{i}" for i in range(len(chunks))],
                                metadatas=[{"source": source}] * len(chunks), embeddings=embeddings)
        else:
            self._collection.add(documents=chunks, ids=[f"{doc_id}_{i}" for i in range(len(chunks))],
                                metadatas=[{"source": source}] * len(chunks))

        self._conn.execute("INSERT INTO kb_docs VALUES (?,?,?,?,?)",
                           (doc_id, source, description, len(chunks), now))
        self._conn.commit()
        return f"✅ 已入库: {source}（{len(chunks)}块，{len(text)}字）"

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """搜索知识库。"""
        if self._use_ds and self._ds_key:
            q_embed = self._deepseek_embed([query])
            results = self._collection.query(query_embeddings=q_embed, n_results=top_k)
        else:
            results = self._collection.query(query_texts=[query], n_results=top_k)

        out = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                out.append({"content": doc[:500], "source": meta.get("source", ""),
                            "score": results["distances"][0][i] if results.get("distances") else 0})
        return out

    def registry(self) -> list[dict]:
        """查询注册表。"""
        rows = self._conn.execute(
            "SELECT source, description, chunks, created_at FROM kb_docs ORDER BY created_at DESC").fetchall()
        return [{"source": r[0], "description": r[1], "chunks": r[2], "created_at": r[3]} for r in rows]

    def remove(self, source: str) -> bool:
        """删除文档（SQLite + ChromaDB）。"""
        row = self._conn.execute(
            "SELECT id, chunks FROM kb_docs WHERE source=?", (source,)
        ).fetchone()
        if not row:
            return False
        doc_id, chunks = row[0], row[1]
        # 删 ChromaDB 向量
        try:
            ids = [f"{doc_id}_{i}" for i in range(chunks)]
            self._collection.delete(ids=ids)
        except Exception:
            pass
        # 删 SQLite
        self._conn.execute("DELETE FROM kb_docs WHERE id=?", (doc_id,))
        self._conn.commit()
        return True

    def _deepseek_embed(self, texts: list[str]) -> list[list[float]]:
        """DeepSeek Embedding API。"""
        import httpx
        resp = httpx.post(
            "https://api.deepseek.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self._ds_key}"},
            json={"model": "deepseek-embed-v4", "input": texts},
            timeout=15,
        )
        data = resp.json()
        return [d["embedding"] for d in data.get("data", [])]

    def close(self):
        self._conn.close()
