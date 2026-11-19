"""
==============================================================================
模块名称: storage/metadata_db.py
功能描述: 基于 SQLite 的文档元数据持久化存储
          记录原始文件名、哈希特征、智能分类、物理归档路径、一句话摘要与标签，
          同时持久化每个切片(Chunk)与源文件/页码的溯源映射关系。
可移植性: 仅使用 Python 内置 sqlite3, json, datetime 模块，零安装开箱即用。
==============================================================================
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import config


class MetadataDB:
    """
    SQLite 元数据管理类
    负责文档信息表 (documents) 和切片溯源表 (document_chunks) 的生命周期管理
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """
        初始化数据库连接并确保数据表已初始化
        :param db_path: sqlite 数据库文件路径，默认使用 config.SQLITE_DB_PATH
        """
        self.db_path = db_path or config.SQLITE_DB_PATH
        self._init_tables()

    def _get_connection(self) -> sqlite3.Connection:
        """
        获取数据库连接，设置 row_factory 为 Row 以便支持字典式访问
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        """
        初始化建表语句
        1. documents: 记录文件级别的信息（分类、物理路径、摘要）
        2. document_chunks: 记录细粒度切片及出处坐标（Slide页码、章节层级）
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. 创建文档总表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    original_filename TEXT NOT NULL,
                    category TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    summary TEXT,
                    tags TEXT,
                    page_count INTEGER DEFAULT 0,
                    file_hash TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 2. 创建切片详情与溯源表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS document_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    source_filename TEXT NOT NULL,
                    chunk_type TEXT NOT NULL,
                    page_or_slide INTEGER NOT NULL,
                    location_label TEXT NOT NULL,
                    content TEXT NOT NULL,
                    vector_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
                );
            """)

            # 3. 创建索引以加速按文件溯源与关键词匹配
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_doc_id 
                ON document_chunks (doc_id);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_docs_category 
                ON documents (category);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_docs_file_hash 
                ON documents (file_hash);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_docs_filename 
                ON documents (original_filename);
            """)

            conn.commit()

    def save_document(
        self,
        doc_id: str,
        original_filename: str,
        category: str,
        stored_path: str,
        summary: str = "",
        tags: Optional[List[str]] = None,
        page_count: int = 0,
        file_hash: str = ""
    ) -> None:
        """
        新增或更新文档元数据记录
        """
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO documents 
                (doc_id, original_filename, category, stored_path, summary, tags, page_count, file_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_id,
                original_filename,
                category,
                stored_path,
                summary,
                tags_json,
                page_count,
                file_hash,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()

    def save_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        """
        批量保存切片与向量数据
        :param chunks: 包含 chunk_id, doc_id, source_filename, chunk_type, 
                       page_or_slide, location_label, content, vector 的列表
        """
        if not chunks:
            return

        with self._get_connection() as conn:
            cursor = conn.cursor()
            records = []
            for c in chunks:
                vec_json = json.dumps(c.get("vector", []))
                records.append((
                    c["chunk_id"],
                    c["doc_id"],
                    c["source_filename"],
                    c.get("chunk_type", "unknown"),
                    c.get("page_or_slide", 1),
                    c.get("location_label", ""),
                    c["content"],
                    vec_json,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))

            cursor.executemany("""
                INSERT OR REPLACE INTO document_chunks
                (chunk_id, doc_id, source_filename, chunk_type, page_or_slide, location_label, content, vector_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, records)
            conn.commit()

    def list_documents(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出所有归档文档，支持按类别过滤
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if category:
                cursor.execute("SELECT * FROM documents WHERE category = ? ORDER BY created_at DESC", (category,))
            else:
                cursor.execute("SELECT * FROM documents ORDER BY created_at DESC")
            
            rows = cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["tags"] = json.loads(item["tags"]) if item["tags"] else []
                results.append(item)
            return results

    def get_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        根据 ID 查询文档详情
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,))
            row = cursor.fetchone()
            if not row:
                return None
            item = dict(row)
            item["tags"] = json.loads(item["tags"]) if item["tags"] else []
            return item

    def get_document_by_hash(self, file_hash: str) -> Optional[Dict[str, Any]]:
        """
        根据内容 SHA256 哈希值查询是否已存在相同内容文档 (秒级防重判据)
        """
        if not file_hash:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE file_hash = ?", (file_hash,))
            row = cursor.fetchone()
            if not row:
                return None
            item = dict(row)
            item["tags"] = json.loads(item["tags"]) if item["tags"] else []
            return item

    def get_document_by_filename(self, filename: str) -> Optional[Dict[str, Any]]:
        """
        根据原始文件名查询文档记录 (版本就地迭代判据)
        """
        if not filename:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE original_filename = ?", (filename,))
            row = cursor.fetchone()
            if not row:
                return None
            item = dict(row)
            item["tags"] = json.loads(item["tags"]) if item["tags"] else []
            return item

    def delete_chunks_by_doc_id(self, doc_id: str) -> int:
        """
        根据 doc_id 级联删除旧版本的所有知识切片 (用于版本就地替换更新)
        :return: 删除的旧切片行数
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM document_chunks WHERE doc_id = ?", (doc_id,))
            conn.commit()
            return cursor.rowcount

    def add_document_alias(self, doc_id: str, new_alias: str) -> None:
        """
        为已存在的文档追加别名标签 (用于异名同内容副本，避免切片重复膨胀)
        """
        doc = self.get_document_by_id(doc_id)
        if not doc:
            return
        tags = doc.get("tags", [])
        alias_tag = f"别名:{new_alias}"
        if alias_tag not in tags:
            tags.append(alias_tag)
            tags_json = json.dumps(tags, ensure_ascii=False)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE documents SET tags = ? WHERE doc_id = ?", (tags_json, doc_id))
                conn.commit()

    def get_all_chunks(self) -> List[Dict[str, Any]]:
        """
        加载所有切片数据（包括其向量表示），供向量检索器载入或构建索引
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chunk_id, doc_id, source_filename, chunk_type, 
                       page_or_slide, location_label, content, vector_json
                FROM document_chunks
            """)
            rows = cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["vector"] = json.loads(item["vector_json"]) if item["vector_json"] else []
                del item["vector_json"]
                results.append(item)
            return results
