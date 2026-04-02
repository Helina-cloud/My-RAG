from __future__ import annotations

import os
import shutil
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from deepseek_embeddings import DeepSeekEmbeddings


@dataclass(frozen=True)
class RagConfig:
    docs_dir: Path
    chroma_dir: Path
    embedding_provider: str
    embedding_model: str
    chunk_size: int = 800
    chunk_overlap: int = 150


def _iter_text_files(docs_dir: Path) -> Iterable[Path]:
    if not docs_dir.exists():
        return []
    exts = {".txt", ".md"}
    return (p for p in docs_dir.rglob("*") if p.is_file() and p.suffix.lower() in exts)


def load_documents(docs_dir: Path) -> List[Document]:
    docs: List[Document] = []
    for path in _iter_text_files(docs_dir):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if not text.strip():
            continue
        docs.append(Document(page_content=text, metadata={"source": str(path)}))
    return docs


def split_documents(
    docs: List[Document], chunk_size: int, chunk_overlap: int
) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    return splitter.split_documents(docs)


def _stable_chunk_ids(chunks: List[Document]) -> List[str]:
    ids: List[str] = []
    for i, d in enumerate(chunks):
        src = str(d.metadata.get("source", ""))
        h = hashlib.sha1((src + "\n" + d.page_content).encode("utf-8", errors="ignore")).hexdigest()
        ids.append(f"{h}:{i}")
    return ids


def make_embeddings(provider: str, model_name: str):
    provider = (provider or "hf").lower().strip()
    if provider in {"deepseek", "ds"}:
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
        if not api_key:
            raise RuntimeError("Missing DEEPSEEK_API_KEY for DeepSeek embeddings.")
        return DeepSeekEmbeddings(api_key=api_key, base_url=base_url, model=model_name)

    # Default: local huggingface sentence-transformers
    from langchain_community.embeddings import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


def load_or_create_chroma(config: RagConfig) -> Chroma:
    embeddings = make_embeddings(config.embedding_provider, config.embedding_model)
    config.chroma_dir.mkdir(parents=True, exist_ok=True)

    vectordb = Chroma(
        persist_directory=str(config.chroma_dir),
        embedding_function=embeddings,
    )

    # Heuristic: if empty, build from docs
    try:
        existing = vectordb._collection.count()  # noqa: SLF001
    except Exception:
        existing = 0

    if existing > 0:
        return vectordb

    docs = load_documents(config.docs_dir)
    if not docs:
        return vectordb

    chunks = split_documents(docs, config.chunk_size, config.chunk_overlap)
    vectordb.add_documents(chunks, ids=_stable_chunk_ids(chunks))
    return vectordb


def rebuild_chroma_from_docs(config: RagConfig) -> Chroma:
    """Delete persisted Chroma and rebuild from docs_dir."""
    if config.chroma_dir.exists():
        shutil.rmtree(config.chroma_dir, ignore_errors=True)
    return load_or_create_chroma(config)


def add_docs_to_chroma(config: RagConfig, docs: List[Document]) -> Tuple[Chroma, int]:
    """Incrementally add given docs into existing Chroma (creates if missing).

    Returns (vectordb, added_chunks_count).
    """
    embeddings = make_embeddings(config.embedding_provider, config.embedding_model)
    config.chroma_dir.mkdir(parents=True, exist_ok=True)
    vectordb = Chroma(
        persist_directory=str(config.chroma_dir),
        embedding_function=embeddings,
    )
    if not docs:
        return vectordb, 0
    chunks = split_documents(docs, config.chunk_size, config.chunk_overlap)
    vectordb.add_documents(chunks, ids=_stable_chunk_ids(chunks))
    return vectordb, len(chunks)


def from_env() -> RagConfig:
    docs_dir = Path(os.getenv("RAG_DOCS_DIR", "docs"))
    chroma_dir = Path(os.getenv("RAG_CHROMA_DIR", "chroma_db"))
    embedding_provider = os.getenv("RAG_EMBEDDING_PROVIDER", "deepseek")
    embedding_model = os.getenv(
        "RAG_EMBEDDING_MODEL",
        "deepseek-embedding"
        if embedding_provider.lower().strip() in {"deepseek", "ds"}
        else "BAAI/bge-small-zh-v1.5",
    )
    # Same override as chat LLM config: keep retrieval and indexing on one model
    if embedding_provider.lower().strip() in {"deepseek", "ds"}:
        embedding_model = os.getenv("DEEPSEEK_EMBEDDING_MODEL", embedding_model)
    return RagConfig(
        docs_dir=docs_dir,
        chroma_dir=chroma_dir,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
    )

