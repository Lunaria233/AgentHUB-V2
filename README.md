# AgentHUB-V2

Self-built multi-agent application platform inspired by the `hello_agents` tutorial, but implemented without depending on the `hello_agents` package.

Current scope:

- Backend platform foundation
- Built-in `chat` app
- Built-in `deep_research` app
- Built-in `SoftWare Engineering Agent` app
- Shared model/history/memory/rag/context/tool/runtime layers

Backend entry:

```bash
cd backend
uvicorn app.main:app --reload
```

Frontend entry:

```bash
cd frontend
npm install
npm run dev
```

Configuration:

- Structured defaults: `backend/config/platform.toml` copied from `backend/config/platform.example.toml`
- Secrets and environment overrides: `backend/.env`
- Frontend API base URL: `frontend/.env.example`
