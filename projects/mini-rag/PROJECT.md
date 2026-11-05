---
name: mini-rag
title: "Mini RAG pilot"
status: en cours
tags: [rag, pilot]
data: "data-lab docs snapshot (4 docs) + 20 questions"
metric:
  key: score
  goal: max
---

## Objectif

Prove the data-lab base end to end on a small, deterministic RAG: a project created with `datalab-new`, its own
env, its chunks in the shared Weaviate under the `MiniRag_` prefix, its runs in the shared MLflow tagged
`project=mini-rag`, and this card showing the best run in the app.

## Approche

- Corpus: a frozen snapshot of data-lab's own `README.md`, `ARCHITECTURE.md`, `decisions.md` and
  `contracts/README.md` (`data/corpus/`), chunked by `##` section then 120-word windows with a 20-word overlap.
- Questions: 20 short factual questions (`data/questions.jsonl`), 2 of them unanswerable from the corpus.
- Retrieval: BM25 and vector (`near_text`, vectors from Weaviate's `text2vec-transformers`, `bge-small-en-v1.5`),
  k = 3 and 5: four configs, one run each in the experiment `mini-rag/retrieval`.
- Generation: `deepseek/deepseek-v4-flash` via OpenRouter by default, or the DGX (Anthropic Messages API,
  temperature 0; the endpoint is logged as `llm_base_url`), told to answer from the passages only or say
  "I don't know".
- Scoring: normalized token-boundary containment; "I don't know" counts as missing; `score = accuracy −
  hallucination`. With 2 unanswerable questions a perfect run scores 0.9, by design (D-7).

## Enseignements

<!-- What the runs taught you, with the run names that show it. -->

## Suite

<!-- Next steps, or why the project stops here. -->
