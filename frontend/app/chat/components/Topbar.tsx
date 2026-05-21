import type { ProviderStatus, User } from "../lib/types";

type TopbarProps = {
  currentUser: User | null;
  isAuthenticated: boolean;
  isDarkMode: boolean;
  providerLabel: string;
  providerStatus: ProviderStatus;
  onNewChat: () => void;
  onSignOut: () => void;
  onToggleTheme: () => void;
};

export function Topbar({
  currentUser,
  isAuthenticated,
  isDarkMode,
  providerLabel,
  providerStatus,
  onNewChat,
  onSignOut,
  onToggleTheme,
}: TopbarProps) {
  return (
    <header className="topbar">
      <div className="topbar-spacer" />
      <div className="provider-status" aria-label={providerLabel}>
        <span aria-hidden="true" className={`status-dot ${providerStatus}`} />
        <span>{providerLabel}</span>
      </div>
      {currentUser ? (
        <div className="user-menu">
          <span>{currentUser.email}</span>
          <button type="button" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      ) : null}
      {isAuthenticated ? (
        <button className="new-chat-button" type="button" onClick={onNewChat}>
          New chat
        </button>
      ) : null}
      <button
        className="theme-toggle"
        type="button"
        aria-label={isDarkMode ? "Switch to light mode" : "Switch to dark mode"}
        aria-pressed={isDarkMode}
        onClick={onToggleTheme}
      >
        <span
          aria-hidden="true"
          className={isDarkMode ? "theme-icon sun-icon" : "theme-icon moon-icon"}
        />
      </button>
    </header>
  );
}
