# __DATALAB_PROJECT__

```bash
uv sync                      # own env; datalab comes from ../../packages/datalab (editable)
cp .env.example .env         # only if you need non-default ports
```

- Identity: `from datalab.project import load; project = load()` reads `PROJECT.md` (fill its sections as you go).
- Runs: `with tracked_run(project, Settings(), "my-run", sub="bm25"):` (`datalab.tracking`) tags `project=<name>`.
- Weaviate: name collections with `collection_name(project.name, "chunks", "bge")` (`datalab.project`).
- Code goes under `src/<your_pkg>/`; the shared stack must be up (`docker compose up -d` at the repo root).
