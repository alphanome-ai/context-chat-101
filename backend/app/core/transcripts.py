import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

import aiofiles
import aiofiles.os

from app.db.models import ChatMessage, ChatSession

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = REPO_ROOT / ".data"


class JsonlTranscriptStore:
    def __init__(self, data_root: Path = DATA_ROOT) -> None:
        self._data_root = data_root

    async def append_records(
        self,
        *,
        service: str,
        session_id: int | str,
        records: Iterable[Mapping[str, Any]],
    ) -> Path:
        session_dir = self._data_root / service / "sessions" / str(session_id)
        transcript_path = session_dir / "messages.jsonl"
        await aiofiles.os.makedirs(session_dir, exist_ok=True)
        await _append_records(transcript_path, list(records))
        return transcript_path


def _chat_session_transcript_service(chat_session: ChatSession) -> str:
    if chat_session.mode == "agent0":
        return "agent0"
    return "chat"


async def append_chat_session_messages_jsonl(
    chat_session: ChatSession,
    messages: Sequence[ChatMessage],
    *,
    store: JsonlTranscriptStore | None = None,
) -> Path:
    transcript_store = store or JsonlTranscriptStore()
    records = [
        {
            "session_id": chat_session.id,
            "user_id": chat_session.user_id,
            "mode": chat_session.mode,
            "model": chat_session.model,
            "message_id": message.id,
            "position": message.position,
            "role": message.role,
            "content": message.content,
            "thinking": message.thinking,
            "events": message.events,
            "input_tokens": message.input_tokens,
            "output_tokens": message.output_tokens,
            "total_tokens": message.total_tokens,
            "created_at": message.created_at,
        }
        for message in messages
    ]
    return await transcript_store.append_records(
        service=_chat_session_transcript_service(chat_session),
        session_id=chat_session.id,
        records=records,
    )


async def _append_records(
    transcript_path: Path,
    records: Sequence[Mapping[str, Any]],
) -> None:
    async with aiofiles.open(transcript_path, "a", encoding="utf-8") as transcript_file:
        for record in records:
            await transcript_file.write(
                json.dumps(
                    record,
                    default=_json_default,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )


def _json_default(value: Any) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
