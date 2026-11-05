# mini-rag

The data-lab pilot: BM25 and vector retrieval over a frozen snapshot of data-lab's docs, answers from an LLM (OpenRouter by default, or the DGX),
scored and logged to the shared MLflow (`mini-rag/retrieval`, tag `project=mini-rag`).

```bash
uv sync
echo 'MINI_RAG_LLM_API_KEY=<openrouter-key>' > .env          # gitignored; required, no default (DGX: .env.example)
uv run python -m mini_rag.run --retrieval bm25 --k 3         # also: vector, --k 5
uv run python -m mini_rag.run --retrieval vector --k 3 --n 2 # smoke run: smoke_* metrics, tag smoke=true
uv run pytest --cov                                          # unit tests, coverage >= 70 %
uv run pytest -m integration                                 # live stack (docker compose up -d at the repo root)
```

Optional settings: `MINI_RAG_GEN_MODEL` (default `deepseek-v4-flash`), `MINI_RAG_GEN_TIMEOUT_S` (60),
`MINI_RAG_MAX_TOKENS` (512). Infra settings are the shared `DATALAB_*` ones.

`data/corpus/` is frozen on purpose: every non-null answer in `data/questions.jsonl` must appear in it verbatim
(a test checks it), so do not refresh it from the live docs.
