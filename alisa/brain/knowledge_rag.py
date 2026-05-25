"""Bilim bazasi (RAG) — shaxsiy hujjatlardan javob berish.

"Mening shartnomamda nima yozilgan?" → PDF/TXT dan javob
"Kompaniya haqida ma'lumot ber" → knowledge base dan

Texnologiya: Chunking + Embedding + Cosine similarity (LLM siz search)
Pi 5 da ishlaydi — katta model kerak emas, oddiy TF-IDF yetarli.
"""

import json
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import structlog

from alisa.core.config import get_config

logger = structlog.get_logger()

KNOWLEDGE_DIR = Path(os.environ.get("ALISA_KNOWLEDGE_DIR", "data/knowledge"))


class KnowledgeBase:
    """Simple RAG — local document search and retrieval."""

    def __init__(self):
        self.documents: List[dict] = []  # {"text": ..., "source": ..., "embedding": ...}
        self._load_documents()

    def _load_documents(self):
        """Load and chunk documents from knowledge directory."""
        try:
            KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            pass
        if not KNOWLEDGE_DIR.exists():
            return

        for file in KNOWLEDGE_DIR.glob("**/*"):
            if file.suffix in (".txt", ".md"):
                self._index_file(file)
            elif file.suffix == ".json":
                self._index_json(file)

        logger.info("knowledge_loaded", documents=len(self.documents))

    def _index_file(self, path: Path):
        """Index a text file by chunking."""
        try:
            text = path.read_text(encoding="utf-8")
            chunks = self._chunk_text(text, chunk_size=500, overlap=50)
            for chunk in chunks:
                self.documents.append({
                    "text": chunk,
                    "source": str(path.name),
                    "embedding": self._compute_embedding(chunk),
                })
        except Exception as e:
            logger.warning("knowledge_index_failed", path=str(path), error=str(e))

    def _index_json(self, path: Path):
        """Index a JSON FAQ file."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    q = item.get("question", item.get("q", ""))
                    a = item.get("answer", item.get("a", ""))
                    text = f"{q} {a}"
                    self.documents.append({
                        "text": text,
                        "source": str(path.name),
                        "embedding": self._compute_embedding(text),
                    })
        except Exception as e:
            logger.warning("knowledge_json_failed", path=str(path), error=str(e))

    def search(self, query: str, top_k: int = 3) -> List[Tuple[str, float]]:
        """Search knowledge base. Returns [(text, score), ...]."""
        if not self.documents:
            return []

        query_emb = self._compute_embedding(query)
        scores = []

        for doc in self.documents:
            score = self._cosine_similarity(query_emb, doc["embedding"])
            scores.append((doc["text"], score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def get_context_for_llm(self, query: str, threshold: float = 0.1) -> Optional[str]:
        """Get relevant context to prepend to LLM prompt."""
        results = self.search(query, top_k=3)
        relevant = [(text, score) for text, score in results if score > threshold]

        if not relevant:
            return None

        context = "Ma'lumot bazasidan topildi:\n"
        for text, score in relevant:
            context += f"- {text[:200]}\n"
        return context

    def add_document(self, text: str, source: str = "manual"):
        """Add a document to knowledge base."""
        chunks = self._chunk_text(text, chunk_size=500, overlap=50)
        for chunk in chunks:
            self.documents.append({
                "text": chunk,
                "source": source,
                "embedding": self._compute_embedding(chunk),
            })

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """Split text into overlapping chunks."""
        words = text.split()
        chunks = []
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i:i + chunk_size])
            if chunk.strip():
                chunks.append(chunk.strip())
        return chunks or [text]

    def _compute_embedding(self, text: str) -> np.ndarray:
        """Compute TF-IDF-like embedding (lightweight, no external deps)."""
        # Simple bag-of-words with character n-grams
        text_lower = text.lower()
        words = re.findall(r"\w+", text_lower)

        # Use word frequency as embedding (fixed size via hashing)
        vec = np.zeros(256)
        for word in words:
            idx = hash(word) % 256
            vec[idx] += 1

        # L2 normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))


_kb: Optional[KnowledgeBase] = None


def get_knowledge_base() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb
