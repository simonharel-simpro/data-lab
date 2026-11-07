# __DATALAB_PROJECT__

```bash
uv sync                      # own env; datalab comes from ../../packages/datalab (editable)
cp .env.example .env         # only if you need non-default ports
```

- Identity: `from datalab.project import load; project = load()` reads `PROJECT.md` (fill its sections as you go).
- Runs: `with tracked_run(project, Settings(), "my-run", sub="bm25"):` (`datalab.tracking`) tags `project=<name>`.
- Weaviate: name collections with `collection_name(project.name, "chunks", "bge")` (`datalab.project`).
- Layout: `configs/` (Hydra: `train.yaml`, `eval.yaml`, groups `paths data model experiment`, optional `hparams_search`),
  `src/__DATALAB_PACKAGE__/` (`train`, `eval` own the I/O; `scoring`, `candidates`, `grid` are pure), `tests/`.
- Train: `uv run python -m __DATALAB_PACKAGE__.train experiment=default [hparams_search=<grid>]` (one parent run, one
  child per candidate and grid combination; a grid is `configs/hparams_search/<name>.yaml`).
- Eval: `uv run python -m __DATALAB_PACKAGE__.eval` (audit only: it reads the test partition when `run.json` allows it).
- Run the experiment with `/experiment`. The shared stack must be up (`docker compose up -d` at the repo root).
