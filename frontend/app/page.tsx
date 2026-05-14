"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { z } from "zod";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  status?: "pending" | "error";
};

type ApiMessage = {
  role: "user" | "assistant";
  content: string;
};

type ProviderStatus = "checking" | "online" | "offline";
type Theme = "light" | "dark";
type AuthMode = "login" | "register";

type LlmOption = {
  id: string;
  label: string;
  providerName: string;
  isDefault?: boolean;
};

const errorResponseSchema = z.object({
  error: z.object({ message: z.string().optional() }).optional(),
  detail: z.union([z.string(), z.array(z.unknown())]).optional(),
});

const authFormSchema = z.object({
  email: z.email("Enter a valid email address."),
  password: z.string().min(8, "Password must be at least 8 characters."),
});

const userSchema = z.object({
  id: z.number(),
  email: z.string(),
  created_at: z.string(),
});

const authResponseSchema = z.object({
  token: z.string(),
  user: userSchema,
});

const llmModelSchema = z.object({
  id: z.string(),
  name: z.string().nullable().optional(),
  isDefault: z.boolean().optional(),
});

const providersResponseSchema = z.object({
  providers: z
    .array(
      z.object({
        name: z.string(),
        models: z.array(llmModelSchema),
      }),
    )
    .optional(),
});

const assistantResponseMessageSchema = z.object({
  content: z.string().nullable().optional(),
  reasoning: z.string().nullable().optional(),
  reasoningContent: z.string().nullable().optional(),
  reasoning_content: z.string().nullable().optional(),
  thinking: z.string().nullable().optional(),
});

const chatCompletionResponseSchema = z.object({
  choices: z
    .array(
      z.object({
        message: assistantResponseMessageSchema.optional(),
      }),
    )
    .optional(),
  error: z.object({ message: z.string().optional() }).optional(),
});

const chatSessionSummarySchema = z.object({
  id: z.number(),
  title: z.string(),
  model: z.string().nullable().optional(),
  updated_at: z.string(),
  message_count: z.number(),
});

const chatSessionDetailSchema = z.object({
  id: z.number(),
  title: z.string(),
  model: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});

const storedChatMessageSchema = z.object({
  id: z.number(),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  thinking: z.string().nullable().optional(),
});

const storedChatSessionSchema = chatSessionDetailSchema.extend({
  messages: z.array(storedChatMessageSchema),
});

const chatSessionSummariesSchema = z.array(chatSessionSummarySchema);

type AssistantResponseMessage = z.infer<typeof assistantResponseMessageSchema>;
type User = z.infer<typeof userSchema>;
type AuthResponse = z.infer<typeof errorResponseSchema>;
type ChatSessionSummary = z.infer<typeof chatSessionSummarySchema>;

const starterPrompts = [
  "Remember that I prefer concise answers.",
  "My project is a context-aware chat app.",
  "What have you learned about me so far?",
];

const AUTH_TOKEN_KEY = "context-chat-token";

function createMessageId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function getErrorMessage(error: unknown) {
  if (error instanceof z.ZodError) {
    return error.issues[0]?.message ?? "The response did not match the expected shape.";
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "The assistant could not respond.";
}

function getApiErrorMessage(payload: AuthResponse, fallback: string) {
  if (payload.error?.message) {
    return payload.error.message;
  }
  if (typeof payload.detail === "string") {
    return payload.detail;
  }
  return fallback;
}

function parseErrorResponse(payload: unknown): AuthResponse {
  return errorResponseSchema.safeParse(payload).data ?? {};
}

function getThinkingText(message?: AssistantResponseMessage) {
  if (!message || typeof message !== "object") {
    return "";
  }

  const fields = [
    message.reasoning,
    message.reasoningContent,
    message.reasoning_content,
    message.thinking,
  ];

  return fields.find((field) => typeof field === "string" && field.trim())
    ?.trim();
}

function splitTaggedThinking(content: string) {
  const match = content.match(/<think(?:ing)?>([\s\S]*?)<\/think(?:ing)?>/i);
  if (!match) {
    return { content: content.trim(), thinking: "" };
  }

  return {
    content: content.replace(match[0], "").trim(),
    thinking: match[1].trim(),
  };
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);
  const [theme, setTheme] = useState<Theme>("light");
  const [authToken, setAuthToken] = useState("");
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [isAuthLoading, setIsAuthLoading] = useState(false);
  const [chatSessions, setChatSessions] = useState<ChatSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [providerLabel, setProviderLabel] = useState("Checking provider");
  const [providerStatus, setProviderStatus] =
    useState<ProviderStatus>("checking");
  const [llmOptions, setLlmOptions] = useState<LlmOption[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const messageListRef = useRef<HTMLDivElement>(null);
  const hasRestoredClientStateRef = useRef(false);

  const canSend = draft.trim().length > 0 && !isSending;
  const hasMessages = messages.length > 0;
  const isDarkMode = theme === "dark";
  const isAuthenticated = Boolean(currentUser && authToken);

  const apiMessages = useMemo<ApiMessage[]>(
    () =>
      messages
        .filter((message) => message.status !== "pending")
        .map((message) => ({
          role: message.role,
          content: message.content,
        })),
    [messages],
  );

  useEffect(() => {
    let isMounted = true;

    async function loadProvider() {
      try {
        const response = await fetch("/api/providers");
        const rawData: unknown = await response.json();
        const data = providersResponseSchema.parse(rawData);
        const nextOptions =
          data.providers?.flatMap((providerItem) =>
            providerItem.models.map((model) => ({
              id: model.id,
              label: model.name ?? model.id,
              providerName: providerItem.name,
              isDefault: model.isDefault,
            })),
          ) ?? [];
        const selectedOption =
          nextOptions.find((option) => option.isDefault) ?? nextOptions[0];

        if (!response.ok) {
          throw new Error("Provider offline");
        }

        if (isMounted) {
          setProviderLabel(
            selectedOption
              ? `${selectedOption.providerName} / ${selectedOption.id}`
              : "Ready",
          );
          setProviderStatus("online");
          setLlmOptions(nextOptions);
          setSelectedModel(selectedOption?.id ?? "");
        }
      } catch {
        if (isMounted) {
          setProviderLabel("Backend offline");
          setProviderStatus("offline");
          setLlmOptions([]);
          setSelectedModel("");
        }
      }
    }

    loadProvider();

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    messageListRef.current?.scrollTo({
      top: messageListRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const getAuthHeaders = useCallback((token = authToken): Record<string, string> => {
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [authToken]);

  const loadChatSessions = useCallback(async (token = authToken) => {
    if (!token) {
      setChatSessions([]);
      return;
    }

    setIsHistoryLoading(true);
    setHistoryError("");

    try {
      const response = await fetch("/api/chat-sessions", {
        headers: getAuthHeaders(token),
      });
      const rawData: unknown = await response.json();

      if (!response.ok) {
        throw new Error(
          getApiErrorMessage(parseErrorResponse(rawData), "Could not load chat history."),
        );
      }

      const data = chatSessionSummariesSchema.parse(rawData);
      setChatSessions(data);
    } catch (error) {
      setHistoryError(getErrorMessage(error));
    } finally {
      setIsHistoryLoading(false);
    }
  }, [authToken, getAuthHeaders]);

  const loadAuthenticatedUser = useCallback(async (token: string) => {
    setIsAuthLoading(true);
    setAuthError("");

    try {
      const response = await fetch("/api/auth/me", {
        headers: getAuthHeaders(token),
      });
      const rawData: unknown = await response.json();

      if (!response.ok) {
        throw new Error(
          getApiErrorMessage(parseErrorResponse(rawData), "Please sign in again."),
        );
      }

      const data = userSchema.parse(rawData);
      setCurrentUser(data);
      await loadChatSessions(token);
    } catch {
      window.localStorage.removeItem(AUTH_TOKEN_KEY);
      setAuthToken("");
      setCurrentUser(null);
      setChatSessions([]);
      setActiveSessionId(null);
    } finally {
      setIsAuthLoading(false);
    }
  }, [getAuthHeaders, loadChatSessions]);

  useEffect(() => {
    if (hasRestoredClientStateRef.current) {
      return;
    }

    hasRestoredClientStateRef.current = true;
    const savedTheme = window.localStorage.getItem("theme");
    if (savedTheme === "light" || savedTheme === "dark") {
      setTheme(savedTheme);
    } else if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
      setTheme("dark");
    }

    const savedToken = window.localStorage.getItem(AUTH_TOKEN_KEY);
    if (savedToken) {
      setAuthToken(savedToken);
      loadAuthenticatedUser(savedToken).finally(() => setIsHydrated(true));
      return;
    }

    setIsHydrated(true);
  }, [loadAuthenticatedUser]);

  async function persistChatTurn(userMessage: Message, assistantMessage: Message) {
    if (!authToken || !currentUser) {
      return;
    }

    const payload = {
      model: selectedModel || undefined,
      messages: [
        {
          role: userMessage.role,
          content: userMessage.content,
        },
        {
          role: assistantMessage.role,
          content: assistantMessage.content,
          thinking: assistantMessage.thinking,
        },
      ],
    };
    const url = activeSessionId
      ? `/api/chat-sessions/${activeSessionId}/messages`
      : "/api/chat-sessions";

    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify(payload),
    });
    const rawData: unknown = await response.json();

    if (!response.ok) {
      throw new Error(
        getApiErrorMessage(parseErrorResponse(rawData), "Could not save chat history."),
      );
    }

    const data = storedChatSessionSchema.parse(rawData);
    setActiveSessionId(data.id);
    await loadChatSessions();
  }

  async function sendMessage(content: string) {
    if (!content) {
      return;
    }

    const userMessage: Message = {
      id: createMessageId(),
      role: "user",
      content,
    };
    const pendingMessage: Message = {
      id: createMessageId(),
      role: "assistant",
      content: "Thinking",
      status: "pending",
    };
    const nextMessages = [...apiMessages, userMessage];

    setMessages((current) => [...current, userMessage, pendingMessage]);
    setDraft("");
    setIsSending(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: nextMessages,
          model: selectedModel || undefined,
        }),
      });
      const rawData: unknown = await response.json();

      if (!response.ok) {
        throw new Error(
          getApiErrorMessage(
            parseErrorResponse(rawData),
            "The backend returned an error.",
          ),
        );
      }

      const data = chatCompletionResponseSchema.parse(rawData);
      const assistantMessage = data.choices?.[0]?.message;
      const { content: assistantContent, thinking: taggedThinking } =
        splitTaggedThinking(assistantMessage?.content ?? "");
      const thinking = [getThinkingText(assistantMessage), taggedThinking]
        .filter(Boolean)
        .join("\n\n");

      if (!assistantContent && !thinking) {
        throw new Error("The assistant response was empty.");
      }

      const assistantMessageForHistory: Message = {
        ...pendingMessage,
        content: assistantContent || "No visible answer returned.",
        thinking: thinking || undefined,
        status: undefined,
      };

      setMessages((current) =>
        current.map((message) =>
          message.id === pendingMessage.id
            ? assistantMessageForHistory
            : message,
        ),
      );

      try {
        await persistChatTurn(userMessage, assistantMessageForHistory);
      } catch (error) {
        setHistoryError(getErrorMessage(error));
      }
    } catch (error) {
      setMessages((current) =>
        current.map((message) =>
          message.id === pendingMessage.id
            ? {
                ...message,
                content: getErrorMessage(error),
                status: "error",
              }
            : message,
        ),
      );
    } finally {
      setIsSending(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    sendMessage(draft.trim());
  }

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsAuthLoading(true);
    setAuthError("");

    try {
      const credentials = authFormSchema.parse({
        email: authEmail.trim().toLowerCase(),
        password: authPassword,
      });
      const response = await fetch(`/api/auth/${authMode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(credentials),
      });
      const rawData: unknown = await response.json();

      if (!response.ok) {
        throw new Error(
          getApiErrorMessage(
            parseErrorResponse(rawData),
            "Could not authenticate with those credentials.",
          ),
        );
      }

      const data = authResponseSchema.parse(rawData);
      window.localStorage.setItem(AUTH_TOKEN_KEY, data.token);
      setAuthToken(data.token);
      setCurrentUser(data.user);
      setAuthPassword("");
      setMessages([]);
      setActiveSessionId(null);
      await loadChatSessions(data.token);
    } catch (error) {
      setAuthError(getErrorMessage(error));
    } finally {
      setIsAuthLoading(false);
    }
  }

  async function loadChatSession(sessionId: number) {
    if (!authToken) {
      return;
    }

    setIsHistoryLoading(true);
    setHistoryError("");

    try {
      const response = await fetch(`/api/chat-sessions/${sessionId}`, {
        headers: getAuthHeaders(),
      });
      const rawData: unknown = await response.json();

      if (!response.ok) {
        throw new Error(
          getApiErrorMessage(parseErrorResponse(rawData), "Could not load this chat."),
        );
      }

      const data = storedChatSessionSchema.parse(rawData);
      setActiveSessionId(data.id);
      setMessages(
        data.messages.map((message) => ({
          id: String(message.id),
          role: message.role,
          content: message.content,
          thinking: message.thinking ?? undefined,
        })),
      );
      setDraft("");
    } catch (error) {
      setHistoryError(getErrorMessage(error));
    } finally {
      setIsHistoryLoading(false);
    }
  }

  async function signOut() {
    if (authToken) {
      await fetch("/api/auth/logout", {
        method: "POST",
        headers: getAuthHeaders(),
      }).catch(() => undefined);
    }

    window.localStorage.removeItem(AUTH_TOKEN_KEY);
    setAuthToken("");
    setCurrentUser(null);
    setChatSessions([]);
    setActiveSessionId(null);
    setMessages([]);
    setDraft("");
  }

  function handleModelChange(modelId: string) {
    const option = llmOptions.find((item) => item.id === modelId);

    setSelectedModel(modelId);

    if (option) {
      setProviderLabel(`${option.providerName} / ${option.id}`);
    }
  }

  function toggleTheme() {
    setTheme((currentTheme) => {
      const nextTheme = currentTheme === "dark" ? "light" : "dark";
      window.localStorage.setItem("theme", nextTheme);
      return nextTheme;
    });
  }

  function startNewChat() {
    setMessages([]);
    setDraft("");
    setActiveSessionId(null);
  }

  if (!isHydrated) {
    return (
      <main className="chat-shell" data-theme={theme}>
        <section className="hydration-stage" aria-live="polite">
          <div className="hydration-loader">
            <span aria-hidden="true" />
            <p>Loading</p>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="chat-shell" data-theme={theme}>
      <header className="topbar">
        <div className="topbar-spacer" />
        <div className="provider-status" aria-label={providerLabel}>
          <span
            aria-hidden="true"
            className={`status-dot ${providerStatus}`}
          />
          <span>{providerLabel}</span>
        </div>
        {currentUser ? (
          <div className="user-menu">
            <span>{currentUser.email}</span>
            <button type="button" onClick={signOut}>
              Sign out
            </button>
          </div>
        ) : null}
        {isAuthenticated ? (
          <button
            className="new-chat-button"
            type="button"
            onClick={startNewChat}
          >
            New chat
          </button>
        ) : null}
        <button
          className="theme-toggle"
          type="button"
          aria-label={isDarkMode ? "Switch to light mode" : "Switch to dark mode"}
          aria-pressed={isDarkMode}
          onClick={toggleTheme}
        >
          <span
            aria-hidden="true"
            className={isDarkMode ? "theme-icon sun-icon" : "theme-icon moon-icon"}
          />
        </button>
      </header>

      {!isAuthenticated ? (
        <section className="auth-stage">
          <form className="auth-card" onSubmit={handleAuthSubmit}>
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
                onChange={(event) => setAuthEmail(event.target.value)}
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
                onChange={(event) => setAuthPassword(event.target.value)}
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
                setAuthMode(authMode === "login" ? "register" : "login");
                setAuthError("");
              }}
            >
              {authMode === "login"
                ? "Need an account? Register"
                : "Already have an account? Sign in"}
            </button>
          </form>
        </section>
      ) : (
        <div className="chat-workspace">
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
                    onClick={() => loadChatSession(session.id)}
                  >
                    <span>{session.title}</span>
                    <small>{session.message_count} messages</small>
                  </button>
                ))
              )}
            </div>
          </aside>

          <section
            className={hasMessages ? "chat-stage with-messages" : "chat-stage"}
          >
            {!hasMessages ? (
              <div className="empty-state">
                <h1>Hey!</h1>
                <div className="starter-list" aria-label="Starter messages">
                  {starterPrompts.map((prompt) => (
                    <button
                      className="starter-chip"
                      key={prompt}
                      type="button"
                      onClick={() => sendMessage(prompt)}
                      disabled={isSending}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="message-list" aria-live="polite" ref={messageListRef}>
                {messages.map((message) => (
                  <article
                    className={`message-bubble ${message.role} ${
                      message.status ?? ""
                    }`}
                    key={message.id}
                  >
                    {message.role === "assistant" && message.thinking ? (
                      <details className="thinking-panel">
                        <summary>Thinking</summary>
                        <div>{message.thinking}</div>
                      </details>
                    ) : null}
                    <div className="message-text">{message.content}</div>
                  </article>
                ))}
              </div>
            )}

            <form className="composer" onSubmit={handleSubmit}>
              <label className="model-picker">
                <span className="sr-only">LLM model</span>
                <select
                  aria-label="LLM model"
                  value={selectedModel}
                  onChange={(event) => handleModelChange(event.target.value)}
                  disabled={isSending || llmOptions.length === 0}
                >
                  {llmOptions.length === 0 ? (
                    <option value="">LLM unavailable</option>
                  ) : (
                    llmOptions.map((option) => (
                      <option
                        key={`${option.providerName}-${option.id}`}
                        value={option.id}
                      >
                        {option.providerName} / {option.label}
                      </option>
                    ))
                  )}
                </select>
              </label>
              <input
                aria-label="Message"
                placeholder="Type a Message"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                disabled={isSending}
              />
              <button type="submit" aria-label="Send message" disabled={!canSend}>
                <span aria-hidden="true" className="arrow-up" />
              </button>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}
