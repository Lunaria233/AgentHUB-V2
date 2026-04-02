# Agent Platform V1 Backend

FastAPI backend for a self-built agent application platform.

Run locally:

```bash
uvicorn app.main:app --reload
```

Configuration:

- `backend/.env` stores secrets and environment-specific overrides.
- `backend/config/platform.toml` stores structured platform/app configuration.
- `backend/.env.example` and `backend/config/platform.example.toml` are reference templates.
