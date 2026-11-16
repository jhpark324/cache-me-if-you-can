"""Request-local model budgets. Provider limits and local policy stay distinct."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable

CLIENT_INPUT_CAP = 131_072
UNKNOWN_MODEL_INPUT_CAP = 32_768
OUTPUT_RESERVE = 4_096
FRAMING_RESERVE = 512


def _positive(value):
    return value if type(value) is int and value > 0 else None


@dataclass(frozen=True)
class ModelBudget:
    model: str | None
    input_limit: int
    output_reserve: int
    source: str
    counter_name: str
    count: Callable[[str], int]

    @classmethod
    def from_metadata(cls, metadata: dict | None):
        metadata = metadata or {}
        context = _positive(metadata.get("context_window"))
        max_input = _positive(metadata.get("max_input_tokens"))
        max_output = _positive(metadata.get("max_output_tokens"))
        reserve = min(OUTPUT_RESERVE, max_output) if max_output else OUTPUT_RESERVE
        candidates = [CLIENT_INPUT_CAP if context or max_input else UNKNOWN_MODEL_INPUT_CAP]
        if max_input:
            candidates.append(max_input)
        if context:
            candidates.append(max(0, context - reserve))
        name = "utf8_bytes_conservative"
        counter = lambda text: len(text.encode("utf-8"))
        # Only an explicit encoding identifier can enable exact local counting.
        # A model slug is not guessed to be equivalent to a public API model.
        encoding = metadata.get("tokenizer")
        if isinstance(encoding, str):
            try:
                import tiktoken
                tokenizer = tiktoken.get_encoding(encoding)
                counter = lambda text: len(tokenizer.encode(text, disallowed_special=()))
                name = encoding
            except (ImportError, ValueError):
                pass
        return cls(metadata.get("model"), min(candidates), reserve,
                   "catalog_with_client_cap" if context or max_input else "conservative_client_cap", name, counter)

    def measure(self, prompt: str, instructions: str) -> int:
        # Count the exact input shape used by the SIWC adapter, not only evidence text.
        envelope = json.dumps({"model": self.model, "instructions": instructions,
                               "input": [{"role": "user", "content": prompt}]}, ensure_ascii=False, separators=(",", ":"))
        return self.count(envelope) + FRAMING_RESERVE

    def fits(self, prompt: str, instructions: str) -> bool:
        return self.measure(prompt, instructions) <= self.input_limit

    def describe(self) -> dict:
        return {"model": self.model, "input_limit": self.input_limit, "output_reserve": self.output_reserve,
                "framing_reserve": FRAMING_RESERVE, "limit_source": self.source, "counter": self.counter_name}
