import type { FormEvent } from "react";

import type { AuthMode } from "../lib/types";

type AuthPanelProps = {
  authEmail: string;
  authError: string;
  authMode: AuthMode;
  authPassword: string;
  isAuthLoading: boolean;
  onEmailChange: (value: string) => void;
  onModeChange: (mode: AuthMode) => void;
  onPasswordChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onClearError: () => void;
};

export function AuthPanel({
  authEmail,
  authError,
  authMode,
  authPassword,
  isAuthLoading,
  onEmailChange,
  onModeChange,
  onPasswordChange,
  onSubmit,
  onClearError,
}: AuthPanelProps) {
  const nextMode = authMode === "login" ? "register" : "login";

  return (
    <section className="auth-stage">
      <form className="auth-card" onSubmit={onSubmit}>
        <div>
          <h1>{authMode === "login" ? "Sign in" : "Create account"}</h1>
          <p>Use an email and password to keep chat history tied to your account.</p>
        </div>
        <label>
          <span>Email</span>
          <input
            type="email"
            autoComplete="email"
            value={authEmail}
            onChange={(event) => onEmailChange(event.target.value)}
            disabled={isAuthLoading}
            required
          />
        </label>
        <label>
          <span>Password</span>
          <input
            type="password"
            autoComplete={authMode === "login" ? "current-password" : "new-password"}
            value={authPassword}
            onChange={(event) => onPasswordChange(event.target.value)}
            disabled={isAuthLoading}
            minLength={8}
            required
          />
        </label>
        {authError ? <p className="auth-error">{authError}</p> : null}
        <button className="auth-submit" type="submit" disabled={isAuthLoading}>
          {isAuthLoading
            ? "Please wait"
            : authMode === "login"
              ? "Sign in"
              : "Create account"}
        </button>
        <button
          className="auth-switch"
          type="button"
          onClick={() => {
            onModeChange(nextMode);
            onClearError();
          }}
        >
          {authMode === "login"
            ? "Need an account? Register"
            : "Already have an account? Sign in"}
        </button>
      </form>
    </section>
  );
}
