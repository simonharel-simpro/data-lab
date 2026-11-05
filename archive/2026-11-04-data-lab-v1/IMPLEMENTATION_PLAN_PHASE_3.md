# Phase 3 — Pilot project `mini-rag` (BM25 + vector, DGX LLM)

**Depends on:** 2A (`datalab` package, `datalab-new`, template) and 2B (the app shows the card + best run).
**Agent:** `general-purpose` (Python 3.12, uv, weaviate-client v4, mlflow, anthropic SDK).
**Repo root:** `/home/simon/projects/data-science/data-lab`. Infra running: `docker compose up -d`.

## Context
The pilot proves the whole base end to end: a project created with `datalab-new`, its own env, data in the shared
Weaviate under its prefix, runs in the shared MLflow tagged `project=mini-rag`, and a card visible in the app with
its best run. Keep it small and deterministic. Decisions: English corpus (D-7); retrieval BM25 **and** vector in v1;
vectors computed by Weaviate's `text2vec-transformers` module (`bge-small-en-v1.5`, D-5) — no embedding code here;
generation by the user's DGX LLM (Anthropic Messages API); scoring = normalized containment, IDK = missing,
`score = accuracy − hallucination`, goal `max` (D-7, U-12).
Reference code to reuse (read before writing): `/home/simon/projects/data-science/Demo-RAG-crag-dataset/src/crag_rag/`
— `index.py:93-113` (count-checked `ensure`), `index.py:137-160` (bm25 / vector search), `llm.py` (DGX client via
`anthropic`), `evaluation.py` + `normalize.py` (outcome rules), `tracking.py:88-98` (metrics logged only at the end).
Check the weaviate-client v4 API for `text2vec_transformers` vectorizer config and `near_text` with Context7.

## Files — `projects/mini-rag/` (created by `datalab-new mini-rag --title "Mini RAG pilot"`, then filled)

#### `PROJECT.md` (from template, FILLED) — `status: en cours`, `tags: [rag, pilot]`, `data: "data-lab docs snapshot
(N docs) + 20 questions"`, `metric: {key: score, goal: max}`; sections Objectif, Approche filled; Enseignements/Suite
left as template comments (not required at `en cours`, so the card shows no badge).

#### `data/corpus/*.md` (NEW) — a frozen snapshot copy of data-lab's own `README.md`, `ARCHITECTURE.md`,
`decisions.md` (and `contracts/README.md`) taken at the start of this phase. Frozen so answers never drift.

#### `data/questions.jsonl` (NEW) — 20 lines `{"id","question","answer"}` written from the snapshot: short factual
answers (a port, a version, a name, a rule), including ≥ 3 numeric answers and ≥ 2 questions whose answer is NOT in
the corpus (expected `"answer": null` → the right output is IDK). Every non-null answer must appear verbatim in the
snapshot (a test checks it).

#### `src/mini_rag/settings.py` (NEW) — `PilotSettings(BaseSettings)`, `env_prefix="MINI_RAG_"`: `dgx_base_url`
(required, no default: validated at startup, F-13), `gen_model="deepseek-v4-flash"`, `gen_timeout_s=60`,
`max_tokens=512`. Infra settings come from `datalab.settings.Settings`.

#### `src/mini_rag/questions.py` (NEW) — `@dataclass(frozen=True) class Question: id: str; question: str; answer: str |
None`. `load_questions(path: Path) -> list[Question]`: one JSON object per non-empty line; missing/extra keys, wrong
types or invalid JSON → `ValueError` naming the line number; duplicate `id` → `ValueError`.

#### `src/mini_rag/corpus.py` (NEW) — load snapshot files; chunk by `##` section then by ~120 words with 20-word
overlap; `Chunk(chunk_id, doc, text)`; pure.

#### `src/mini_rag/index.py` (NEW) — `EMBEDDER: Final = "bge-small-en-v1.5"` (must match the compose image, D-5).
`index_name(embedder: str, size: int, overlap: int) -> str` = `datalab.project.collection_name("mini-rag", "t2v",
embedder, f"w{size}o{overlap}")` (embedder id in the parts, U-13). `ensure_collection(client: WeaviateClient, chunks:
list[Chunk], *, size: int, overlap: int, embedder: str = EMBEDDER) -> str`: name = `index_name(...)`; create with vectorizer `text2vec_transformers` + properties `text`, `chunk_id`, `doc`; ingest; verify
object count == len(chunks), else delete and rebuild once, then raise (Demo-RAG `ensure` pattern, F-13).
`search(client, name, query, mode: Literal["bm25","vector"], k) -> list[Chunk]` (`bm25` or `near_text`).

#### `src/mini_rag/generate.py` (NEW) — **port** Demo-RAG `llm.py` `AnthropicMessagesClient` + `strip_thinking`
(`llm.py:59-64,66-109`), trimmed of usage accounting. The DGX returns a `thinking` block before the text and may
also inline `<think>…</think>`: `content[0].text` would be wrong (B1).
`class GenerationError(RuntimeError)`. `class DgxGenerator: __init__(self, base_url: str, model: str, *, timeout_s:
float, max_tokens: int, http_client: httpx2.Client | None = None)` (builds `anthropic.Anthropic(base_url=…,
api_key="not-needed", timeout=…, max_retries=2, http_client=…)`); `answer(self, question: str, passages:
list[Chunk]) -> str`: system prompt = answer briefly from the passages only, reply exactly `I don't know` if they
don't contain the answer; `messages.create(..., extra_body={"temperature": 0})` (anthropic ≥ 2 dropped `temperature`
from the signature; the DGX honours it — deterministic runs); text = join of blocks with `type == "text"` only, then
`strip_thinking`; empty → `GenerationError`; `anthropic.APIError` → `GenerationError` (F-13).

#### `src/mini_rag/scoring.py` (NEW) — **reuse, don't re-specify** (B-3). Copy into the pilot, with attribution in
a comment, Demo-RAG `normalize.py`'s `normalize` (NFKC, lowercase, drop apostrophes so "don't" → "dont", punctuation
→ space, drop articles, collapse spaces), `contains_phrase` (**token-boundary** containment: `5050` does not match
`50505`) and `parse_number` / `numbers_equal`; and the IDK detection of `evaluation.py:20-23,72`
(`_IDK_VARIANTS = (normalize("i don't know"), normalize("i do not know"))`, matched with `contains_phrase`). No bare
`unknown` variant (it would turn correct answers containing the word into `missing`).
`outcome(pred: str, expected: str | None) -> Literal["correct","missing","hallucination"]`, rules in order:
IDK → `missing`; expected `None` (unanswerable) → `hallucination`; `numbers_equal(pred, expected)` → `correct`;
`contains_phrase(normalize(pred), normalize(expected))` → `correct`; else `hallucination`.
`metrics(outcomes) -> {"accuracy","hallucination","missing","score"}` with `score = accuracy − hallucination` (D-7).
Note for the card: with 2 unanswerable questions and IDK = missing, a perfect run scores **0.9**, by design (D-7).

#### `src/mini_rag/run.py` (NEW) — `def run(project: Project, settings: Settings, pilot: PilotSettings, questions:
list[Question], *, retrieval: Literal["bm25","vector"], k: int, n: int | None, size: int, overlap: int, collection:
str, answer: Callable[[str, list[Chunk]], str], search: Callable[[str, Literal["bm25","vector"], int], list[Chunk]])
-> str` (`size`/`overlap`/`collection` feed `config_hash` and params; returns the run id; tests inject
fake `answer`/`search`); `def main(argv: list[str] | None = None) -> int` is the thin CLI
(`uv run python -m mini_rag.run --retrieval bm25|vector --k 3|5 [--n N]`): `datalab.project.load()`, `PilotSettings()`,
`Settings()`, `preflight(settings.mlflow_tracking_uri)`, `ensure_collection`, builds the real `DgxGenerator` and
`search`, calls `run`. Inside `tracked_run(project, settings, run_name=f"{retrieval}-k{k}", sub="retrieval",
tags={"config_hash": …})`: `config_hash` = sha256 of `json.dumps` of `{retrieval, k, n, questions_hash, gen_model,
max_tokens, size, overlap, collection}` (sorted keys); log those as params (`questions_hash` = sha256 of the selected
question ids); answer every
question; any `GenerationError` → exception propagates → run FAILED, **no metrics logged**; metrics logged once all
questions are scored (F-13). **Partial runs (D-15):** when `n` < the number of questions, every metric is logged
with a `smoke_` prefix (`smoke_score`, `smoke_accuracy`, …) and the run gets tag `smoke=true`, so it never competes
with `score` in the app (the app ranks on the exact key only). Log per-question results as a JSON artifact.
Each file ≤ 200 lines.

#### `pyproject.toml` (MODIFY, from template) — **declare every package the pilot imports directly** (the
declared-deps rule): `anthropic==2.3.0`, `httpx2` (anthropic 2.3's HTTP client; tests use its `MockTransport`),
`weaviate-client`, `mlflow==3.17.2`, `pydantic-settings` — same versions as `datalab`'s lock, uv resolves them once;
dev `pytest`, `pytest-cov`. Pytest `addopts` includes `--cov=mini_rag --cov-fail-under=70 -m 'not integration'`.
Commit `uv.lock`.

#### `tests/` (NEW) — unit only by default; integration marked.

#### `.github/workflows/ci.yml` (MODIFY) — job `pilot`: `cd projects/mini-rag && uv sync && uv run pytest` (unit).
#### `README.md` (MODIFY, root) — "Pilot" paragraph: how to run the 4 configs and see them in the app.
#### `ARCHITECTURE.md` (MODIFY) — Data flow section: the pilot as the concrete end-to-end example.

## Tests

| Test | Given → expected | Source |
|---|---|---|
| `test_u_12_containment_counts_as_correct` | pred `"The MLflow port is 5050."`, expected `"5050"` → `correct` | U-12 |
| `test_b_3_token_boundary_rejects_longer_number` | pred `"port 50505"`, expected `"5050"` → `hallucination` | B-3 |
| `test_u_12_numeric_normalisation` | pred `"1,200"`, expected `"1200"` → `correct` (via `numbers_equal`) | U-12 |
| `test_u_12_idk_is_missing_not_wrong` | pred `"I don't know."` and `"I do not know"`, expected `"5050"` → `missing` | U-12, B-3 |
| `test_b_3_word_unknown_is_not_idk` | pred `"The unknown port is 5050"`, expected `"5050"` → `correct` | B-3 |
| `test_u_12_answer_to_unanswerable_is_hallucination` | expected `None`, pred `"8080"` → `hallucination`; pred IDK → `missing` | U-12 |
| `test_u_12_score_formula` | outcomes 6 correct, 2 hallucination, 2 missing → accuracy 0.6, hallucination 0.2, score 0.4 | D-7 |
| `test_questions_answers_are_in_snapshot` | every non-null `answer` appears verbatim in `data/corpus/` | data integrity |
| `test_load_questions_valid_file` | 2 lines `{"id":"q1","question":"…","answer":"5050"}`, `{"id":"q2",…,"answer":null}` → 2 `Question`s, `q2.answer is None` | loader |
| `test_load_questions_malformed_line_raises` | line 2 is `{"id":"q2"}` → `ValueError` mentioning line 2; duplicate id → `ValueError` | loader |
| `test_u_13_embedder_id_is_part_of_collection_hash` | `index_name("bge-small-en-v1.5", 120, 20)` ≠ `index_name("other", 120, 20)`; both start `MiniRag_` | U-13 |
| `test_chunking_overlap_and_ids_stable` | fixed doc → same chunk ids twice; consecutive chunks share 20 words | corpus |
| `test_f_13_missing_dgx_base_url_fails_at_settings` | env without `MINI_RAG_DGX_BASE_URL` → `ValidationError` before any I/O | F-13 |
| `test_f_13_wrong_shape_200_raises_not_empty_answer` | `DgxGenerator(..., http_client=httpx2.Client(transport=httpx2.MockTransport(h)))` (pattern: Demo-RAG `tests/test_llm.py:30-41`), 200 `{"content": []}` → `GenerationError` | F-13 |
| `test_b1_thinking_block_stripped` | content `[{"type":"thinking","thinking":"x","signature":"s"}, {"type":"text","text":"<think>y</think>5050"}]` → `answer(...) == "5050"` (pattern: `test_llm.py:55-59`) | B1 |
| `test_b1_api_error_becomes_generation_error` | MockTransport 500 → `GenerationError` | F-13 |
| `test_f_13_generation_error_marks_run_failed_without_metrics` | MLflow at `sqlite:///{tmp_path}/mlflow.db`, generator raising at question 3 → run FAILED, no `score` metric | F-13 |
| `test_run_logs_project_tag_and_experiment` | sqlite MLflow, fake generator → run in `mini-rag/retrieval` with `project=mini-rag`, `score` present | contract |
| `test_d_15_partial_run_logs_smoke_metrics_only` | sqlite MLflow, fake generator, `--n 2` → metrics `smoke_score` etc., **no** `score`; tag `smoke=true`; params `n=2`, `questions_hash` set | D-15 |
| `test_g_8_template_card_is_idee_missing_objectif` (in `app/src/lib/completeness.test.ts`, added here because both 2A and 2B now exist) | read `new URL('../../../templates/project/PROJECT.md', import.meta.url)` (repo root is 3 levels above `app/src/lib/`), replace `__DATALAB_PROJECT__`→`demo` and `__DATALAB_TITLE__`→`"Demo"`, split frontmatter, parse it with the `yaml` devDep, then `cardSchema.parse` → valid, `status === "idée"`; `missing(card, body)` → `["Objectif"]` | G-8 |
| `test_integration_bm25_and_vector_return_hits` (`integration`) | ensure index, `search(...,"bm25",3)` and `("vector",3)` for "Which port does MLflow use?" → ≥ 1 chunk mentioning 5050 | end to end |

## Acceptance (manual, record outputs)
Run the 4 configs (`bm25`/`vector` × k 3/5) against the real DGX → 4 FINISHED runs in MLflow at 127.0.0.1:5050 under
`mini-rag/retrieval`, all tagged; `cd app && npm run dev` → the `mini-rag` card shows "score = …, Meilleur de 4 runs"
with a working link (dev mode); `npm run build` → same value, run name without link (D-14); collections visible in Weavit UI under the `MiniRag_` prefix.

<!-- plan-validate: READY 2026-11-03 sha256:2650e72d4c27 -->
