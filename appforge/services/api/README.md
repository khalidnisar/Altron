# AppForge AI — API and agents

FastAPI service plus the eight autonomous agents that drive the pipeline.

## Layout

```
appforge/
  agents/          discovery, analysis, design, development,
                   testing, publishing, monetization, growth
  routers/         REST endpoints (apps, projects, pipeline)
  services/        providers, scoring, review mining, code generation
  models.py        SQLAlchemy schema
  orchestrator.py  task queue dispatch
  worker.py        long-running queue drainer
  seed.py          demo data + full pipeline run
```

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
export APPFORGE_DATABASE_URL="sqlite:///./dev.db"
uvicorn appforge.main:app --reload
pytest
```

Interactive docs are served at `/docs`.

## Offline mode

If no LLM key is configured the service reports `offline_mode: true` at
`/api/health` and every external provider falls back to a deterministic stub.
The whole pipeline still runs, which is what makes the test suite hermetic.
