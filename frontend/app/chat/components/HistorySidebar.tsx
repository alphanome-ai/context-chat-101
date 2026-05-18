import type { ChatSessionSummary } from "../lib/types";
import {
  formatLocalHistoryTimestamp,
  getUtcTimestampValue,
} from "../lib/utils";

type HistorySidebarProps = {
  activeSessionId: number | null;
  chatSessions: ChatSessionSummary[];
  historyError: string;
  isHistoryLoading: boolean;
  onLoadSession: (sessionId: number) => void;
};

export function HistorySidebar({
  activeSessionId,
  chatSessions,
  historyError,
  isHistoryLoading,
  onLoadSession,
}: HistorySidebarProps) {
  return (
    <aside className="history-sidebar" aria-label="Chat history">
      <div className="history-header">
        <span>History</span>
        {isHistoryLoading ? <span>Loading</span> : null}
      </div>
      {historyError ? <p className="history-error">{historyError}</p> : null}
      <div className="history-list">
        {chatSessions.length === 0 ? (
          <p className="history-empty">No saved chats yet.</p>
        ) : (
          chatSessions.map((session) => (
            <button
              className={
                session.id === activeSessionId
                  ? "history-item active"
                  : "history-item"
              }
              key={session.id}
              type="button"
              onClick={() => onLoadSession(session.id)}
            >
              <span>{session.title}</span>
              <small>
                <time dateTime={getUtcTimestampValue(session.updated_at)}>
                  {formatLocalHistoryTimestamp(session.updated_at)}
                </time>
              </small>
              <small>{session.message_count} messages</small>
            </button>
          ))
        )}
      </div>
    </aside>
  );
}
