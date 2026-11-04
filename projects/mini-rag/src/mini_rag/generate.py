"""Answers from the user's DGX LLM over the Anthropic Messages API.

Ported from Demo-RAG `llm.py` (`strip_thinking`, `AnthropicMessagesClient`), trimmed of usage accounting. The DGX
returns a `thinking` block before the text and may inline `<think>...</think>`, so `content[0].text` is wrong (B1).
"""

import re
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


class DgxGenerator:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout_s: float,
        max_tokens: int,
        http_client: httpx2.Client | None = None,
    ) -> None:
        self.model, self.max_tokens = model, max_tokens
        self.sdk = anthropic.Anthropic(
            base_url=base_url,
            api_key="not-needed",  # placeholder: the LAN DGX is unauthenticated and ignores it
            timeout=timeout_s,
            max_retries=2,
            http_client=http_client,
        )

    def answer(self, question: str, passages: list[Chunk]) -> str:
        try:
            message = self.sdk.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM,
                messages=[{"role": "user", "content": _prompt(question, passages)}],
                # anthropic>=2 dropped `temperature` from the signature; the DGX honours it: deterministic runs.
                extra_body={"temperature": 0},
            )
        except anthropic.APIError as err:
            raise GenerationError(f"dgx {self.model}: {err}") from err
        text = strip_thinking("".join(getattr(b, "text", "") for b in message.content or [] if b.type == "text"))
        if not text:
            raise GenerationError(f"dgx {self.model}: no text in response")
        return text
