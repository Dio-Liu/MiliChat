import sqlite3
import time
import numpy as np
import json
from typing import List, Dict, Any, Optional
# 引入向量模型库
from sentence_transformers import SentenceTransformer

class MemoryStore:
    def __init__(self, db_path: str = "memory.sqlite"):
        self.db_path = db_path
        print("正在加载 Embedding 模型 (首次运行可能需要下载)...")
        # 加载轻量级中文友好模型，下载后会缓存到本地
        # 'all-MiniLM-L6-v2' 是英文最强轻量模型
        # 'paraphrase-multilingual-MiniLM-L12-v2' 支持中文更好，但稍大
        # 这里推荐用多语言版本，或者专门的中文模型 'shibing624/text2vec-base-chinese'
        # 为了通用和稳定，我们先用多语言版:
        self.encoder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        print("模型加载完成。")
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        # 新增 embedding 列 (BLOB 类型用于存二进制向量)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            mtype TEXT NOT NULL,
            key TEXT,
            value TEXT,
            importance REAL DEFAULT 0.5,
            embedding BLOB,  
            created_at INTEGER NOT NULL
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_type ON memories(mtype);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_key ON memories(key);")
        conn.commit()
        conn.close()

    def get_latest_by_key(self, key: str) -> Optional[Dict[str, Any]]:
        # 这个函数不需要改，依然用于精确查找
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        row = cur.execute("""
            SELECT id, text, mtype, key, value, importance, created_at
            FROM memories
            WHERE key = ? AND value IS NOT NULL AND value != ''
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        """, (key,)).fetchone()
        conn.close()

        if not row:
            return None
        return {
            "id": row[0], "text": row[1], "mtype": row[2], "key": row[3], "value": row[4],
            "importance": row[5], "created_at": row[6]
        }

    def add_memory(self, text: str, mtype: str = "fact", key: str = "", value: str = "",
                   importance: float = 0.5) -> int:
        ts = int(time.time())
        
        # 1. 计算向量
        # encode 返回的是 numpy array
        vector = self.encoder.encode(text)
        # 2. 转为二进制 blob
        vector_blob = vector.tobytes()

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # ★★★ 对于 fact 类型且有 key 的记忆，需要先删除旧的同名记忆（保证唯一性）★★★
        if mtype == "fact" and key:
            # 查找是否已存在相同 key 的记忆
            existing = cur.execute("""
                SELECT id FROM memories 
                WHERE mtype = 'fact' AND key = ?
            """, (key,)).fetchall()
            
            if existing:
                # 删除所有旧的同名记忆
                old_ids = [row[0] for row in existing]
                print(f"🔄 [Memory] 更新 fact: {key} -> {value} (删除 {len(old_ids)} 条旧记录)")
                placeholders = ','.join(['?'] * len(old_ids))
                cur.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", old_ids)
            else:
                print(f"✨ [Memory] 新增 fact: {key} -> {value}")
        
        # 插入新记忆
        cur.execute("""
        INSERT INTO memories(text, mtype, key, value, importance, embedding, created_at)
        VALUES(?,?,?,?,?,?,?)
        """, (text, mtype, key, value, importance, vector_blob, ts))
        conn.commit()
        mid = cur.lastrowid
        conn.close()
        return mid

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        向量检索实现：
        1. 把 query 转成向量
        2. 取出数据库所有向量
        3. 计算余弦相似度
        4. 返回 Top K
        """
        q = query.strip()
        if not q:
            return []

        # 1. 计算查询向量
        query_vector = self.encoder.encode(q) # shape: (384,)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # 2. 取出所有记录 (对于个人桌面应用，哪怕几万条记录，全部取出来算一次相似度也是毫秒级的)
        # 如果数据量真的很大(>10万)，才需要考虑 pgvector 或 chroma
        rows = cur.execute("SELECT id, text, mtype, key, value, importance, created_at, embedding FROM memories").fetchall()
        conn.close()

        if not rows:
            return []

        # 3. 解析数据库中的向量
        # 我们构建一个矩阵来批量计算
        db_vectors = []
        metadata = []
        
        for r in rows:
            blob = r[7]
            if not blob:
                continue
            # 从 bytes 转回 numpy array
            vec = np.frombuffer(blob, dtype=np.float32)
            db_vectors.append(vec)
            metadata.append({
                "id": r[0], "text": r[1], "mtype": r[2], "key": r[3], 
                "value": r[4], "importance": r[5], "created_at": r[6]
            })

        if not db_vectors:
            return []

        db_matrix = np.array(db_vectors) # shape: (N, 384)

        # 4. 计算余弦相似度
        # Cosine Similarity = (A . B) / (||A|| * ||B||)
        # sentence-transformers 的向量通常已经归一化了(norm=1)，所以直接点积即可
        # 如果不确定，可以手动除以范数
        
        # 简单点积 (Dot Product)
        scores = np.dot(db_matrix, query_vector)
        
        # 5. 排序并取 Top K
        # argsort 返回的是从小到大的索引，所以要 [::-1] 反转
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            score = scores[idx]
            # 只有相似度超过一定阈值才算相关 (比如 0.3 或 0.4)
            if score > 0.3: 
                item = metadata[idx]
                item["score"] = float(score) # 把分数也带上方便调试
                results.append(item)
        
        return results