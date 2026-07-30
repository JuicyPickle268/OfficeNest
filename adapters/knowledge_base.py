"""
知识库——ChromaDB 向量存储 + SQLite 注册表。
纯本地嵌入（all-MiniLM-L6-v2），首次自动下载 79MB 模型缓存。
"""
import os
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")  # 国内加速
import sqlite3, uuid, json
from pathlib import Path
from datetime import datetime, timezone


class KnowledgeBase:
    """本地向量知识库——ChromaDB 默认嵌入，纯本地免费。"""

    def __init__(self, db_path: str = "./data/mother.db", persist_dir: str = "./data/kb"):
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS kb_docs (
            id TEXT PRIMARY KEY, source TEXT, description TEXT,
            chunks INTEGER, created_at REAL)""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS kb_fulltext (
            id TEXT PRIMARY KEY, source TEXT, text TEXT, created_at REAL)""")
        self._conn.commit()

        import chromadb
        self._chroma = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._chroma.get_or_create_collection("office_kb")

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

        # ChromaDB 默认本地嵌入（all-MiniLM-L6-v2，首次自动下载79MB缓存）
        self._collection.add(
            documents=chunks,
            ids=[f"{doc_id}_{i}" for i in range(len(chunks))],
            metadatas=[{"source": source}] * len(chunks),
        )

        self._conn.execute("INSERT INTO kb_docs VALUES (?,?,?,?,?)",
                           (doc_id, source, description, len(chunks), now))
        self._conn.execute("INSERT INTO kb_fulltext VALUES (?,?,?,?)",
                           (doc_id, source, text, now))
        self._conn.commit()
        return f"✅ 已入库: {source}（{len(chunks)}块，{len(text)}字）"

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """搜索知识库。"""
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
        self._conn.execute("DELETE FROM kb_fulltext WHERE id=?", (doc_id,))
        self._conn.commit()
        return True

    def read(self, source: str) -> str:
        """读取文档全文。"""
        row = self._conn.execute(
            "SELECT text FROM kb_fulltext WHERE source=?", (source,)
        ).fetchone()
        return row[0] if row else f"❌ 未找到: {source}"

    def close(self):
        self._conn.close()
