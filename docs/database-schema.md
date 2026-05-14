# Database Schema

The backend uses SQLite with SQLAlchemy models in `backend/app/db/models.py`.

## Tables

### `users`

Stores registered application users.

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| `id` | `INTEGER` | Primary key, indexed | User id |
| `email` | `VARCHAR(320)` | Required, unique, indexed | Normalized lowercase email |
| `password_hash` | `VARCHAR(512)` | Required | PBKDF2 password hash |
| `created_at` | `DATETIME` | Required | UTC creation timestamp |

### `auth_sessions`

Stores active login sessions.

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| `id` | `INTEGER` | Primary key | Session row id |
| `user_id` | `INTEGER` | Required, indexed, foreign key | References `users.id` |
| `token_hash` | `VARCHAR(64)` | Required, unique, indexed | SHA-256 hash of bearer token |
| `created_at` | `DATETIME` | Required | UTC creation timestamp |
| `expires_at` | `DATETIME` | Required | Session expiry timestamp |

### `chat_sessions`

Stores one chat thread per user.

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| `id` | `INTEGER` | Primary key, indexed | Chat session id |
| `user_id` | `INTEGER` | Required, indexed, foreign key | References `users.id` |
| `title` | `VARCHAR(160)` | Required | Generated from the first user message |
| `model` | `VARCHAR(120)` | Optional | Selected LLM model |
| `created_at` | `DATETIME` | Required | UTC creation timestamp |
| `updated_at` | `DATETIME` | Required | Updated when messages are appended |

### `chat_messages`

Stores ordered messages within a chat session.

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| `id` | `INTEGER` | Primary key, indexed | Message id |
| `session_id` | `INTEGER` | Required, indexed, foreign key | References `chat_sessions.id` |
| `role` | `VARCHAR(24)` | Required | `user` or `assistant` |
| `content` | `TEXT` | Required | Visible message text |
| `thinking` | `TEXT` | Optional | Model reasoning/thinking text |
| `position` | `INTEGER` | Required | Message order inside session |
| `created_at` | `DATETIME` | Required | UTC creation timestamp |

Unique constraint: `chat_messages(session_id, position)`.

## Relationships

- `users` -> `auth_sessions`: one-to-many
- `users` -> `chat_sessions`: one-to-many
- `chat_sessions` -> `chat_messages`: one-to-many

Deleting a user cascades to auth sessions and chat sessions. Deleting a chat session cascades to its messages.
