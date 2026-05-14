# Context Chat API

FastAPI backend scaffolded with an application-factory layout.

## Requirements

- Python 3.14
- uv

## Local Setup

```bash
cp .env.example .env
uv sync
```

## Run

```bash
uv run python main.py
```

Alternative FastAPI CLI:

```bash
uv run fastapi dev app/main.py
```

The API exposes:

- `GET /api/health`
- `GET /api/meta`
- `GET /api/v1/status`
- `GET /api/v1/llm-provider/providers`
- `POST /api/v1/llm-provider/chat/completion`

Docs are available at `/docs` when `DEBUG=true`.

## LLM Provider

Configure the upstream OpenAI-compatible provider with:

```bash
LLM_BASE_URL="https://api.openai.com/v1"
LLM_API_KEY="..."
LLM_DEFAULT_MODEL="gpt-4o-mini"
LLM_AVAILABLE_MODELS="gpt-4o-mini,gpt-4o"
```

Use `model: "default"` in chat requests to resolve to `LLM_DEFAULT_MODEL`.

The same LLM routes are also available under `/api/v1/llm/*` as a shorter alias.

## Structure

```txt
app/
  api/       # root and versioned routers
  core/      # settings, logging, middleware, request context
  db/        # database integration
  services/  # domain services
  shared/    # shared schemas, models, utilities
```
