"""Explicitly prepared, pinned KURE-v2 CPU embeddings. Never truncates queries."""
from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
from threading import RLock

MODEL_ID = "nlpai-lab/KURE-v2"
MODEL_REVISION = "3431f86d399d666083890dbb882aced6708873bc"
DOCUMENT_TOKENS = 512
QUERY_TOKENS = 64
TOKEN_DIMENSION = 128


class EmbeddingError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}


class KureEmbedding:
    """Model loading/download occurs only in prepare(), called by a user action."""

    def __init__(self, model_path: str | Path | None = None):
        self.model_path = Path(model_path).expanduser() if model_path else None
        self.model = None
        self._lock = RLock()
        self.error_code = None

    @property
    def ready(self) -> bool:
        return self.model is not None

    def prepare(self) -> None:
        with self._lock:
            if self.ready:
                return
            try:
                import torch
                from huggingface_hub import snapshot_download
                from sentence_transformers import MultiVectorEncoder

                path = self.model_path
                if path is not None:
                    # A cache directory is supported, but only the pinned snapshot is read.
                    candidates = [path / "models--nlpai-lab--KURE-v2" / "snapshots" / MODEL_REVISION,
                                  path / "snapshots" / MODEL_REVISION, path]
                    path = next((p for p in candidates if p.name == MODEL_REVISION and (p / "config.json").is_file()), None)
                    if path is None:
                        raise EmbeddingError("MODEL_NOT_READY", "고정된 KURE-v2 모델 파일을 찾을 수 없습니다.")
                else:
                    path = Path(snapshot_download(MODEL_ID, revision=MODEL_REVISION))
                torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
                model = MultiVectorEncoder(str(path), device="cpu", local_files_only=True,
                    model_kwargs={"dtype": torch.float32, "attn_implementation": "sdpa"})
                model[0].document_length = DOCUMENT_TOKENS
                expansion = model[0].query_expansion or {}
                if model[0].query_length not in (None, QUERY_TOKENS) or expansion.get("length") != QUERY_TOKENS:
                    raise EmbeddingError("EMBEDDING_PROFILE_MISMATCH", "모델의 질의 길이가 프로필과 다릅니다.")
                self.model = model
                # Warm-up verifies real finite multi-vector output before readiness.
                self.encode_query("검색 준비 확인")
                self.error_code = None
            except EmbeddingError:
                self.model = None
                raise
            except ImportError as exc:
                self.model = None
                self.error_code = "EMBEDDING_DEPENDENCIES_MISSING"
                raise EmbeddingError(self.error_code, "임베딩 실행 의존성을 설치한 뒤 다시 준비해 주세요.") from exc
            except Exception as exc:
                self.model = None
                self.error_code = "MODEL_PREPARATION_FAILED"
                raise EmbeddingError(self.error_code, "임베딩 모델을 준비하지 못했습니다. 설치와 모델 경로를 확인해 주세요.") from exc

    def _require(self):
        if self.model is None:
            raise EmbeddingError("INDEX_NOT_READY", "설정에서 검색 모델을 먼저 준비해 주세요.")
        return self.model

    def count_tokens(self, text: str, kind: str = "document") -> int:
        model = self._require()
        return len(model.tokenizer.encode(model.prompts.get(kind, "") + text, add_special_tokens=True, truncation=False))

    def offsets(self, text: str) -> list[tuple[int, int]]:
        return self._require().tokenizer(text, add_special_tokens=False, truncation=False,
                                        return_offsets_mapping=True)["offset_mapping"]

    def _validate(self, value):
        import numpy as np
        array = np.asarray(value, dtype=np.float32)
        if array.ndim != 2 or not len(array) or array.shape[1] != TOKEN_DIMENSION or not np.isfinite(array).all():
            raise EmbeddingError("EMBEDDING_PROFILE_MISMATCH", "유효한 다중 벡터를 생성하지 못했습니다.")
        norms = np.linalg.norm(array, axis=1, keepdims=True)
        if (norms <= 0).any():
            raise EmbeddingError("EMBEDDING_PROFILE_MISMATCH", "유효하지 않은 토큰 벡터입니다.")
        return array / norms

    def encode_query(self, text: str):
        if not isinstance(text, str) or not text.strip():
            raise EmbeddingError("VALIDATION_ERROR", "검색어를 입력해 주세요.")
        with self._lock:
            length = self.count_tokens(text, "query")
            if length > QUERY_TOKENS:
                raise EmbeddingError("QUERY_TOO_LONG", "검색 질의를 의미별로 짧게 나눠 주세요.",
                                     {"token_count": length, "token_budget": QUERY_TOKENS})
            result = self._require().encode_query(text, batch_size=1, convert_to_numpy=True, show_progress_bar=False)
            return self._validate(result)

    def encode_documents(self, texts: list[str]):
        with self._lock:
            for text in texts:
                if self.count_tokens(text) > DOCUMENT_TOKENS:
                    raise EmbeddingError("DOCUMENT_TOO_LONG", "청크의 임베딩 입력 예산을 초과했습니다.")
            return [self._validate(v) for v in self._require().encode_document(
                texts, batch_size=4, convert_to_numpy=True, show_progress_bar=False)]

    def configuration(self) -> dict:
        self._require()
        return {"representation": "multi_vector", "token_dimension": TOKEN_DIMENSION,
                "dtype": "float32", "device": "cpu", "metric": "cosine", "scoring": "maxsim",
                "normalization": "token_l2", "query_tokens": QUERY_TOKENS,
                "document_tokens": DOCUMENT_TOKENS, "overlap_tokens": 64,
                "context_tokens": 64, "chunk_rules_version": "markdown-v1",
                "query_policy": "reject_over_budget-v1", "sentence_boundary": "punctuation-v1",
                "markdown_parser": "markdown-it-py/commonmark+table",
                "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
                "prompts": dict(self.model.prompts), "query_expansion": self.model[0].query_expansion,
                "runtime_versions": {name: importlib.metadata.version(name) for name in
                    ("sentence-transformers", "transformers", "torch", "markdown-it-py", "lancedb")}}
