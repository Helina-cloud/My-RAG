from __future__ import annotations

import time
from typing import List, Optional

from langchain_core.embeddings import Embeddings


class DeepSeekEmbeddings(Embeddings):
    """DeepSeek embeddings via OpenAI-compatible API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-embedding",
        timeout: float = 60.0,
        max_retries: int = 3,
        batch_size: int = 64,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.batch_size = batch_size

        # Lazy import: langchain-openai usually brings openai package.
        from openai import OpenAI  # type: ignore

        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)

    def _embed(self, texts: List[str]) -> List[List[float]]:
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                resp = self._client.embeddings.create(model=self.model, input=texts)
                # Ensure stable ordering by index
                data = sorted(resp.data, key=lambda x: x.index)
                return [d.embedding for d in data]
            except Exception as e:  # noqa: BLE001
                last_err = e
                msg = str(e).lower()
                if "no matched path" in msg or "matched path" in msg:
                    raise RuntimeError(
                        "DeepSeek Embedding 请求失败（网关返回 No matched path）："
                        "当前账号/接口可能未开放与 OpenAI 兼容的 embeddings，或路径与官方不一致。"
                        "请改用本地向量：在环境变量或 Streamlit Secrets 中设置 "
                        "RAG_EMBEDDING_PROVIDER=hf，RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5，"
                        "并删除旧向量库后重新「入库」或勾选重建。"
                    ) from e
                if attempt < self.max_retries - 1:
                    time.sleep(0.8 * (2**attempt))
                    continue
                raise
        raise RuntimeError(str(last_err))

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for i in range(0, len(texts), self.batch_size):
            out.extend(self._embed(texts[i : i + self.batch_size]))
        return out

    def embed_query(self, text: str) -> List[float]:
        return self._embed([text])[0]

