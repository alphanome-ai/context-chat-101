# Context Chat Backend

FastAPI backend for email/password auth, SQLite chat sessions, and llm-chat completions.

## Setup

```bash
cp .env.example .env
uv sync
```

Configure `.env`:

```bash
LLM_BASE_URL="https://api.openai.com/v1"
LLM_API_KEY="..."
```

Available providers and models are defined in the Python LLM registry under
`app/core/llm`, not in environment variables.

SQLite is used by default at `context_chat.db`.

## Run

```bash
uv run fastapi dev
```

## Database migrations

Install dependencies after pulling migration changes:

```bash
uv sync
```

Apply migrations:

```bash
uv run alembic upgrade head
```

Create a new migration after changing SQLAlchemy models:

```bash
uv run alembic revision --autogenerate -m "describe change"
```

Review the generated file under `alembic/versions/`, then apply it with:

```bash
uv run alembic upgrade head
```
