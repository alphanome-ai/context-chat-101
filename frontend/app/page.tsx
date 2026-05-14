"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

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

type ChatCompletionResponse = {
  choices?: Array<{
    message?: {
      content?: string | null;
      reasoning?: string | null;
      reasoningContent?: string | null;
      reasoning_content?: string | null;
      thinking?: string | null;
    };
  }>;
  error?: {
    message?: string;
  };
};

type AssistantResponseMessage = NonNullable<
  NonNullable<ChatCompletionResponse["choices"]>[number]["message"]
>;

type ProvidersResponse = {
  providers?: Array<{
    name: string;
    models: Array<{
      id: string;
      name?: string | null;
      isDefault?: boolean;
    }>;
  }>;
};

type ProviderStatus = "checking" | "online" | "offline";
type Theme = "light" | "dark";

type LlmOption = {
  id: string;
  label: string;
  providerName: string;
  isDefault?: boolean;
};

const starterPrompts = [
  "Remember that I prefer concise answers.",
  "My project is a context-aware chat app.",
  "What have you learned about me so far?",
];

function createMessageId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function getErrorMessage(error: unknown) {
  if (error instanceof Error) {
    return error.message;
  }

  return "The assistant could not respond.";
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
  const [theme, setTheme] = useState<Theme>("light");
  const [providerLabel, setProviderLabel] = useState("Checking provider");
  const [providerStatus, setProviderStatus] =
    useState<ProviderStatus>("checking");
  const [llmOptions, setLlmOptions] = useState<LlmOption[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const messageListRef = useRef<HTMLDivElement>(null);

  const canSend = draft.trim().length > 0 && !isSending;
  const hasMessages = messages.length > 0;
  const isDarkMode = theme === "dark";

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
        const data = (await response.json()) as ProvidersResponse;
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
    const savedTheme = window.localStorage.getItem("theme");

    if (savedTheme === "light" || savedTheme === "dark") {
      setTheme(savedTheme);
      return;
    }

    if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
      setTheme("dark");
    }
  }, []);

  useEffect(() => {
    messageListRef.current?.scrollTo({
      top: messageListRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

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
      const data = (await response.json()) as ChatCompletionResponse;

      if (!response.ok) {
        throw new Error(
          data.error?.message ?? "The backend returned an error.",
        );
      }

      const assistantMessage = data.choices?.[0]?.message;
      const { content: assistantContent, thinking: taggedThinking } =
        splitTaggedThinking(assistantMessage?.content ?? "");
      const thinking = [getThinkingText(assistantMessage), taggedThinking]
        .filter(Boolean)
        .join("\n\n");

      if (!assistantContent && !thinking) {
        throw new Error("The assistant response was empty.");
      }

      setMessages((current) =>
        current.map((message) =>
          message.id === pendingMessage.id
            ? {
                ...message,
                content: assistantContent || "No visible answer returned.",
                thinking: thinking || undefined,
                status: undefined,
              }
            : message,
        ),
      );
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
        <button
          className="new-chat-button"
          type="button"
          onClick={startNewChat}
        >
          New chat
        </button>
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
    </main>
  );
}
