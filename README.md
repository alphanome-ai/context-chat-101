# Context Chat

Chat/agent app.

## Apps

- `frontend/` - Next.js chat UI
- `backend/` - FastAPI API, auth, SQLite persistence, LLM proxy

## Run locally

Start the backend:

```bash
cd backend
cp .env.example .env
uv sync
uv run fastapi dev
```

Start the frontend:

```bash
cd frontend
cp .env.example .env
bun install
bun dev
```

Frontend expects `BACKEND_API_URL` in `frontend/.env`.
