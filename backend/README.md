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
LLM_DEFAULT_MODEL="gpt-4o-mini"
LLM_AVAILABLE_MODELS="gpt-4o-mini,gpt-4o"
```

SQLite is used by default at `context_chat.db`.

## Run

```bash
uv run fastapi dev
```
