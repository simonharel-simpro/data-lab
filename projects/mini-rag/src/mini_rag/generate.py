"""Answers from an LLM over the Anthropic Messages API: OpenRouter by default, or the user's LAN DGX.

Ported from Demo-RAG `llm.py` (`strip_thinking`, `AnthropicMessagesClient`), trimmed of usage accounting. Reasoning
models return a `thinking` block before the text and may inline `<think>...</think>`, so `content[0].text` is wrong
(B1).
"""

import re
from collections import Counter
from typing import Final

import anthropic
import httpx2

from mini_rag.corpus import Chunk

_THINK_BLOCK: Final = re.compile(r"<think>.*?</think>", re.DOTALL)
SYSTEM: Final = (
    "Answer the question briefly, using only the passages given. "
    "If the passages do not contain the answer, reply exactly: I don't know"
)


class GenerationError(RuntimeError):
    pass


def strip_thinking(text: str) -> str:
    text = _THINK_BLOCK.sub("", text)
    # Some servers drop the opening tag and only emit the closing one.
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    return text.strip()


def _prompt(question: str, passages: list[Chunk]) -> str:
    body = "\n\n".join(f"[{i}] ({p.doc}) {p.text}" for i, p in enumerate(passages, start=1))
    return f"Passages:\n{body}\n\nQuestion: {question}"


class LlmGenerator:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str | None,
        timeout_s: float,
        max_tokens: int,
        providers: list[str] | None = None,
        quantization: str | None = None,
        max_retries: int = 2,
        http_client: httpx2.Client | None = None,
    ) -> None:
        self.model, self.max_tokens = model, max_tokens
        # anthropic>=2 dropped `temperature` from the signature; both endpoints honour it.
        self.extra_body: dict[str, object] = {"temperature": 0}
        if providers:
            # OpenRouter routing: only these upstreams, in order, never outside the list or the quantization.
            routing: dict[str, object] = {"order": providers, "allow_fallbacks": False}
            if quantization:
                routing["quantizations"] = [quantization]
            self.extra_body["provider"] = routing
        # Which upstream served each answer (OpenRouter's `provider` response field); empty elsewhere.
        self.served: Counter[str] = Counter()
        self.sdk = anthropic.Anthropic(
            base_url=base_url,
            api_key=api_key or "not-needed",  # placeholder: the LAN DGX is unauthenticated and ignores it
            timeout=timeout_s,
            max_retries=max_retries,
            http_client=http_client,
        )

    def answer(self, question: str, passages: list[Chunk]) -> str:
        try:
            message = self.sdk.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM,
                messages=[{"role": "user", "content": _prompt(question, passages)}],
                extra_body=self.extra_body,
            )
        except anthropic.APIError as err:
            raise GenerationError(f"llm {self.model}: {err}") from err
        if not isinstance(message, anthropic.types.Message):
            raise GenerationError(f"llm {self.model}: malformed response ({type(message).__name__})")
        if message.stop_reason == "max_tokens":
            raise GenerationError(
                f"llm {self.model}: answer truncated at max_tokens={self.max_tokens}; raise MINI_RAG_MAX_TOKENS"
            )
        served = (message.model_extra or {}).get("provider")
        if isinstance(served, str):
            self.served[served] += 1
        text = strip_thinking("".join(getattr(b, "text", "") for b in message.content or [] if b.type == "text"))
        if not text:
            raise GenerationError(f"llm {self.model}: no text in response")
        return text
