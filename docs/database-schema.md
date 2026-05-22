# Database Schema

The backend uses SQLite with SQLAlchemy models in `backend/app/db/models.py`.

Application user IDs and chat session IDs are UUID strings. Message row IDs,
auth-session row IDs, and quota-usage row IDs remain integer primary keys.

## Tables

### `users`

Stores registered application users.

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| `id` | `VARCHAR(36)` | Primary key, indexed | User UUID |
| `email` | `VARCHAR(320)` | Required, unique, indexed | Normalized lowercase email |
| `password_hash` | `VARCHAR(512)` | Required | PBKDF2 password hash |
| `created_at` | `DATETIME` | Required | UTC creation timestamp |

### `auth_sessions`

Stores active login sessions.

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| `id` | `INTEGER` | Primary key | Session row id |
| `user_id` | `VARCHAR(36)` | Required, indexed, foreign key | References `users.id` |
| `token_hash` | `VARCHAR(64)` | Required, unique, indexed | SHA-256 hash of bearer token |
| `created_at` | `DATETIME` | Required | UTC creation timestamp |
| `expires_at` | `DATETIME` | Required | Session expiry timestamp |

### `chat_sessions`

Stores one chat thread per user.

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| `id` | `VARCHAR(36)` | Primary key, indexed | Chat session UUID |
| `user_id` | `VARCHAR(36)` | Required, indexed, foreign key | References `users.id` |
| `title` | `VARCHAR(160)` | Required | Generated from the first user message |
| `model` | `VARCHAR(120)` | Optional | Selected LLM model |
| `mode` | `VARCHAR(24)` | Required, default `chat` | `chat` or `agent0` |
| `created_at` | `DATETIME` | Required | UTC creation timestamp |
| `updated_at` | `DATETIME` | Required | Updated when messages are appended |

### `chat_messages`

Stores ordered messages within a chat session.

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| `id` | `INTEGER` | Primary key, indexed | Message id |
| `session_id` | `VARCHAR(36)` | Required, indexed, foreign key | References `chat_sessions.id` |
| `role` | `VARCHAR(24)` | Required | `user` or `assistant` |
| `content` | `TEXT` | Required | Visible message text |
| `thinking` | `TEXT` | Optional | Model reasoning/thinking text |
| `events_json` | `TEXT` | Optional | JSONL structured agent events |
| `input_tokens` | `INTEGER` | Optional | Input token usage for assistant responses |
| `output_tokens` | `INTEGER` | Optional | Output token usage for assistant responses |
| `total_tokens` | `INTEGER` | Optional | Total token usage for assistant responses |
| `position` | `INTEGER` | Required | Message order inside session |
| `created_at` | `DATETIME` | Required | UTC creation timestamp |

Unique constraint: `chat_messages(session_id, position)`.

### `quota_usage`

Tracks aggregate token usage by user and date.

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| `id` | `INTEGER` | Primary key, indexed | Quota row id |
| `user_id` | `VARCHAR(36)` | Required, indexed, foreign key | References `users.id` |
| `date` | `DATETIME` | Required | Usage date |
| `tokens_used` | `INTEGER` | Required | Total tokens used |

## Relationships

- `users` -> `auth_sessions`: one-to-many
- `users` -> `chat_sessions`: one-to-many
- `users` -> `quota_usage`: one-to-many
- `chat_sessions` -> `chat_messages`: one-to-many

Deleting a user cascades to auth sessions and chat sessions. Deleting a chat session cascades to its messages.

## Transcript Storage

Database persistence is the source of truth for chat history. The app also
appends JSONL transcript records through `backend/app/core/transcripts.py`.

Transcript path:

```text
.data/<service>/sessions/<session_id>/messages.jsonl
```

For chat sessions:

```text
.data/chat/sessions/<chat-session-uuid>/messages.jsonl
```

For agent0 sessions:

```text
.data/agent0/sessions/<chat-session-uuid>/messages.jsonl
```

The transcript writer is service-based, so future services can write to paths
such as `.data/agent2/sessions/<id>/messages.jsonl`.
