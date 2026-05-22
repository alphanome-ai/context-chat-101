"use client";

import {
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  AUTH_TOKEN_KEY,
  chatModeOptions,
  PROVIDER_STATUS_POLL_INTERVAL_MS,
} from "./lib/constants";
import {
  authFormSchema,
  authResponseSchema,
  chatCompletionResponseSchema,
  chatSessionSummariesSchema,
  providersResponseSchema,
  storedChatSessionSchema,
  userSchema,
} from "./lib/schemas";
import {
  getThinkingText,
  normalizeTokenUsage,
  readStreamingAssistantResponse,
  splitTaggedThinking,
} from "./lib/streaming";
import type {
  AuthMode,
  ChatMode,
  ChatSessionSummary,
  LlmOption,
  Message,
  PickerMenu,
  ProviderStatus,
  Theme,
  TokenUsage,
  User,
} from "./lib/types";
import {
  createMessageId,
  extractHtmlPreview,
  getApiErrorMessage,
  getErrorMessage,
  isMessageListNearBottom,
  readJsonResponse,
  shouldOpenDraftEditor,
  writeClipboardText,
} from "./lib/utils";

export function useChatController() {
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
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [providerLabel, setProviderLabel] = useState("Checking backend");
  const [providerStatus, setProviderStatus] =
    useState<ProviderStatus>("checking");
  const [llmOptions, setLlmOptions] = useState<LlmOption[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [selectedMode, setSelectedMode] = useState<ChatMode>("chat");
  const [openPicker, setOpenPicker] = useState<PickerMenu | null>(null);
  const [activeHtmlPreviewMessageId, setActiveHtmlPreviewMessageId] = useState<
    string | null
  >(null);
  const [expandedMessageIds, setExpandedMessageIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [copiedItemId, setCopiedItemId] = useState<string | null>(null);
  const [isDraftEditorOpen, setIsDraftEditorOpen] = useState(false);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const messageListRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLFormElement>(null);
  const draftInputRef = useRef<HTMLTextAreaElement>(null);
  const expandedDraftInputRef = useRef<HTMLTextAreaElement>(null);
  const hasRestoredClientStateRef = useRef(false);
  const copyFeedbackTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const isMessageListAtBottomRef = useRef(true);
  const activeStreamAbortControllerRef = useRef<AbortController | null>(null);

  const canSend = draft.trim().length > 0 && !isSending;
  const hasMessages = messages.length > 0;
  const isDarkMode = theme === "dark";
  const isAuthenticated = Boolean(currentUser && authToken);
  const selectedModeLabel =
    chatModeOptions.find((option) => option.id === selectedMode)?.label ??
    "Chat";
  const selectedModelOption = llmOptions.find(
    (option) => option.id === selectedModel,
  );
  const selectedModelLabel = selectedModelOption
    ? selectedModelOption.label
    : "LLM unavailable";
  const isModelPickerDisabled = isSending || llmOptions.length === 0;
  const sessionTokenUsage = useMemo<TokenUsage>(
    () =>
      messages.reduce<TokenUsage>(
        (total, message) => {
          if (!message.tokenUsage) {
            return total;
          }

          return {
            inputTokens: total.inputTokens + message.tokenUsage.inputTokens,
            outputTokens: total.outputTokens + message.tokenUsage.outputTokens,
            totalTokens: total.totalTokens + message.tokenUsage.totalTokens,
          };
        },
        { inputTokens: 0, outputTokens: 0, totalTokens: 0 },
      ),
    [messages],
  );
  const activeHtmlPreview = useMemo(() => {
    if (!activeHtmlPreviewMessageId) {
      return null;
    }

    const message = messages.find(
      (item) =>
        item.id === activeHtmlPreviewMessageId &&
        item.role === "assistant" &&
        !item.status,
    );

    return message ? extractHtmlPreview(message.content, message.id) : null;
  }, [activeHtmlPreviewMessageId, messages]);

  const getAuthHeaders = useCallback(
    (token = authToken): Record<string, string> => {
      return token ? { Authorization: `Bearer ${token}` } : {};
    },
    [authToken],
  );

  const loadChatSessions = useCallback(
    async (token = authToken) => {
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
        const rawData = await readJsonResponse(response);

        if (!response.ok) {
          throw new Error(
            getApiErrorMessage(rawData, "Could not load chat history."),
          );
        }

        const data = chatSessionSummariesSchema.parse(rawData);
        setChatSessions(data);
      } catch (error) {
        setHistoryError(getErrorMessage(error));
      } finally {
        setIsHistoryLoading(false);
      }
    },
    [authToken, getAuthHeaders],
  );

  const loadAuthenticatedUser = useCallback(
    async (token: string) => {
      setIsAuthLoading(true);
      setAuthError("");

      try {
        const response = await fetch("/api/auth/me", {
          headers: getAuthHeaders(token),
        });
        const rawData = await readJsonResponse(response);

        if (!response.ok) {
          throw new Error(getApiErrorMessage(rawData, "Please sign in again."));
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
    },
    [getAuthHeaders, loadChatSessions],
  );

  useEffect(() => {
    let isMounted = true;
    let isCheckingStatus = false;

    async function checkApiStatus() {
      if (isCheckingStatus) {
        return;
      }

      isCheckingStatus = true;

      try {
        const response = await fetch("/api/status", { cache: "no-store" });

        if (!response.ok) {
          throw new Error("Backend offline");
        }

        if (isMounted) {
          setProviderLabel("Online");
          setProviderStatus("online");
        }
      } catch {
        if (isMounted) {
          setProviderLabel("Offline");
          setProviderStatus("offline");
        }
      } finally {
        isCheckingStatus = false;
      }
    }

    async function loadProvider() {
      try {
        const response = await fetch("/api/providers");
        const rawData = await readJsonResponse(response);
        const data = providersResponseSchema.parse(rawData);
        const nextOptions =
          data.providers?.flatMap((providerItem) =>
            providerItem.models.map((model) => ({
              id: model.id,
              label: model.displayName ?? model.name ?? model.id,
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
          setLlmOptions(nextOptions);
          setSelectedModel((currentModel) =>
            nextOptions.some((option) => option.id === currentModel)
              ? currentModel
              : (selectedOption?.id ?? ""),
          );
        }
      } catch {
        if (isMounted) {
          setLlmOptions([]);
          setSelectedModel("");
        }
      }
    }

    checkApiStatus();
    loadProvider();
    const providerStatusInterval = window.setInterval(
      checkApiStatus,
      PROVIDER_STATUS_POLL_INTERVAL_MS,
    );

    return () => {
      isMounted = false;
      window.clearInterval(providerStatusInterval);
    };
  }, []);

  useEffect(() => {
    const messageList = messageListRef.current;

    if (!messageList) {
      return;
    }

    if (!isMessageListAtBottomRef.current) {
      setShowScrollToBottom(true);
      return;
    }

    messageList.scrollTo({
      top: messageList.scrollHeight,
      behavior: "smooth",
    });
    setShowScrollToBottom(false);
  }, [messages]);

  useEffect(() => {
    if (isDraftEditorOpen) {
      expandedDraftInputRef.current?.focus();
    }
  }, [isDraftEditorOpen]);

  useEffect(() => {
    return () => {
      if (copyFeedbackTimeoutRef.current) {
        clearTimeout(copyFeedbackTimeoutRef.current);
      }
      activeStreamAbortControllerRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (activeHtmlPreviewMessageId && !activeHtmlPreview) {
      setActiveHtmlPreviewMessageId(null);
    }
  }, [activeHtmlPreview, activeHtmlPreviewMessageId]);

  useEffect(() => {
    if (!openPicker) {
      return;
    }

    function handlePointerDown(event: MouseEvent) {
      if (!composerRef.current?.contains(event.target as Node)) {
        setOpenPicker(null);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpenPicker(null);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [openPicker]);

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

  function resetConversationUi() {
    setActiveHtmlPreviewMessageId(null);
    setExpandedMessageIds(new Set());
    setCopiedItemId(null);
    setIsDraftEditorOpen(false);
    isMessageListAtBottomRef.current = true;
    setShowScrollToBottom(false);
  }

  async function persistChatTurn(
    userMessage: Message,
    assistantMessage: Message,
  ) {
    if (!authToken || !currentUser) {
      return;
    }

    const payload = {
      model: selectedModel || undefined,
      ...(activeSessionId ? {} : { mode: selectedMode }),
      messages: [
        {
          role: userMessage.role,
          content: userMessage.content,
        },
        {
          role: assistantMessage.role,
          content: assistantMessage.content,
          thinking: assistantMessage.thinking,
          input_tokens: assistantMessage.tokenUsage?.inputTokens,
          output_tokens: assistantMessage.tokenUsage?.outputTokens,
          total_tokens: assistantMessage.tokenUsage?.totalTokens,
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
    const rawData = await readJsonResponse(response);

    if (!response.ok) {
      throw new Error(
        getApiErrorMessage(rawData, "Could not save chat history."),
      );
    }

    const data = storedChatSessionSchema.parse(rawData);
    setActiveSessionId(data.id);
    await loadChatSessions();
  }

  async function sendMessage(content: string) {
    if (!content || isSending) {
      return;
    }

    const abortController = new AbortController();
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
    isMessageListAtBottomRef.current = true;
    setShowScrollToBottom(false);
    setMessages((current) => [...current, userMessage, pendingMessage]);
    setDraft("");
    setIsDraftEditorOpen(false);
    setIsSending(true);
    activeStreamAbortControllerRef.current = abortController;

    let latestAssistantContent = "";
    let latestThinking = "";
    let latestTokenUsage: TokenUsage | undefined;

    try {
      const response = await fetch(
        selectedMode === "agent0" ? "/api/agent0" : "/api/chat",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...getAuthHeaders(),
          },
          body: JSON.stringify({
            session_id: activeSessionId,
            message: userMessage.content,
            model: selectedModel || undefined,
          }),
          signal: abortController.signal,
        },
      );
      const contentType = response.headers.get("Content-Type") ?? "";

      if (!response.ok) {
        const rawData = await readJsonResponse(response);
        throw new Error(
          getApiErrorMessage(rawData, "The backend returned an error."),
        );
      }

      let assistantContent = "";
      let thinking = "";
      let tokenUsage: TokenUsage | undefined;
      let wasStopped = false;

      if (contentType.includes("text/event-stream")) {
        const streamedMessage = await readStreamingAssistantResponse(
          response,
          (nextMessage) => {
            latestAssistantContent =
              nextMessage.content === "Thinking" && nextMessage.thinking
                ? ""
                : nextMessage.content;
            latestThinking = nextMessage.thinking ?? "";
            latestTokenUsage = nextMessage.tokenUsage;
            setMessages((current) =>
              current.map((message) =>
                message.id === pendingMessage.id
                  ? {
                      ...message,
                      content: nextMessage.content,
                      thinking: nextMessage.thinking,
                      tokenUsage: nextMessage.tokenUsage,
                      status: "streaming",
                    }
                  : message,
              ),
            );
          },
          { signal: abortController.signal },
        );

        assistantContent = streamedMessage.content;
        thinking = streamedMessage.thinking ?? "";
        tokenUsage = streamedMessage.tokenUsage;
        wasStopped = streamedMessage.stopped;
      } else {
        const rawData = await readJsonResponse(response);
        const data = chatCompletionResponseSchema.parse(rawData);
        const assistantMessage = data.choices?.[0]?.message;
        const { content: fullContent, thinking: taggedThinking } =
          splitTaggedThinking(assistantMessage?.content ?? "");

        assistantContent = fullContent;
        thinking = [getThinkingText(assistantMessage), taggedThinking]
          .filter(Boolean)
          .join("\n\n");
        tokenUsage = normalizeTokenUsage(data.usage);
      }

      const assistantMessageForHistory: Message = {
        ...pendingMessage,
        content:
          assistantContent ||
          (wasStopped
            ? "Stopped before a response was received."
            : "No visible answer returned."),
        thinking: thinking || undefined,
        tokenUsage,
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
      if (abortController.signal.aborted) {
        const stoppedAssistantMessage: Message = {
          ...pendingMessage,
          content:
            latestAssistantContent || "Stopped before a response was received.",
          thinking: latestThinking || undefined,
          tokenUsage: latestTokenUsage,
          status: undefined,
        };

        setMessages((current) =>
          current.map((message) =>
            message.id === pendingMessage.id
              ? stoppedAssistantMessage
              : message,
          ),
        );

        try {
          await persistChatTurn(userMessage, stoppedAssistantMessage);
        } catch (persistError) {
          setHistoryError(getErrorMessage(persistError));
        }
        return;
      }

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
      if (activeStreamAbortControllerRef.current === abortController) {
        activeStreamAbortControllerRef.current = null;
      }
      setIsSending(false);
    }
  }

  function stopStreaming() {
    activeStreamAbortControllerRef.current?.abort();
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    sendMessage(draft.trim());
  }

  function handleDraftKeyDown(event: ReactKeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage(draft.trim());
    }
  }

  function handleDraftChange(value: string) {
    setDraft(value);

    if (!isDraftEditorOpen && shouldOpenDraftEditor(value)) {
      setIsDraftEditorOpen(true);
    }
  }

  function handleMessageListScroll() {
    const messageList = messageListRef.current;

    if (!messageList) {
      return;
    }

    const isAtBottom = isMessageListNearBottom(messageList);
    isMessageListAtBottomRef.current = isAtBottom;
    setShowScrollToBottom(!isAtBottom);
  }

  function scrollMessageListToBottom() {
    const messageList = messageListRef.current;

    if (!messageList) {
      return;
    }

    isMessageListAtBottomRef.current = true;
    setShowScrollToBottom(false);
    messageList.scrollTo({
      top: messageList.scrollHeight,
      behavior: "smooth",
    });
  }

  function toggleMessageExpansion(messageId: string) {
    setExpandedMessageIds((current) => {
      const next = new Set(current);

      if (next.has(messageId)) {
        next.delete(messageId);
      } else {
        next.add(messageId);
      }

      return next;
    });
  }

  async function copyToClipboard(content: string, itemId: string) {
    const trimmedContent = content.trim();

    if (!trimmedContent) {
      return;
    }

    try {
      await writeClipboardText(trimmedContent);
    } catch {
      return;
    }

    setCopiedItemId(itemId);

    if (copyFeedbackTimeoutRef.current) {
      clearTimeout(copyFeedbackTimeoutRef.current);
    }

    copyFeedbackTimeoutRef.current = setTimeout(() => {
      setCopiedItemId(null);
      copyFeedbackTimeoutRef.current = null;
    }, 1600);
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
      const rawData = await readJsonResponse(response);

      if (!response.ok) {
        throw new Error(
          getApiErrorMessage(
            rawData,
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
      resetConversationUi();
      setActiveSessionId(null);
      await loadChatSessions(data.token);
    } catch (error) {
      setAuthError(getErrorMessage(error));
    } finally {
      setIsAuthLoading(false);
    }
  }

  async function loadChatSession(sessionId: string) {
    if (!authToken) {
      return;
    }

    setIsHistoryLoading(true);
    setHistoryError("");

    try {
      const response = await fetch(`/api/chat-sessions/${sessionId}`, {
        headers: getAuthHeaders(),
      });
      const rawData = await readJsonResponse(response);

      if (!response.ok) {
        throw new Error(
          getApiErrorMessage(rawData, "Could not load this chat."),
        );
      }

      const data = storedChatSessionSchema.parse(rawData);
      setActiveSessionId(data.id);
      setSelectedMode(data.mode);
      resetConversationUi();
      setMessages(
        data.messages.map((message) => ({
          id: String(message.id),
          role: message.role,
          content: message.content,
          thinking: message.thinking ?? undefined,
          tokenUsage:
            message.input_tokens != null &&
            message.output_tokens != null &&
            message.total_tokens != null
              ? {
                  inputTokens: message.input_tokens,
                  outputTokens: message.output_tokens,
                  totalTokens: message.total_tokens,
                }
              : undefined,
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
    resetConversationUi();
    setDraft("");
  }

  function handleModelChange(modelId: string) {
    setSelectedModel(modelId);
    setOpenPicker(null);
  }

  function handleModeChange(mode: ChatMode) {
    if (mode !== selectedMode && messages.length > 0) {
      setMessages([]);
      setDraft("");
      setActiveSessionId(null);
      resetConversationUi();
    }
    setSelectedMode(mode);
    setOpenPicker(null);
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
    resetConversationUi();
  }

  return {
    state: {
      activeHtmlPreview,
      activeSessionId,
      authEmail,
      authError,
      authMode,
      authPassword,
      canSend,
      chatSessions,
      copiedItemId,
      currentUser,
      draft,
      expandedMessageIds,
      hasMessages,
      historyError,
      isAuthenticated,
      isAuthLoading,
      isDarkMode,
      isDraftEditorOpen,
      isHistoryLoading,
      isHydrated,
      isModelPickerDisabled,
      isSending,
      llmOptions,
      messages,
      openPicker,
      providerLabel,
      providerStatus,
      selectedMode,
      selectedModeLabel,
      selectedModel,
      selectedModelLabel,
      sessionTokenUsage,
      showScrollToBottom,
      theme,
    },
    refs: {
      composerRef,
      draftInputRef,
      expandedDraftInputRef,
      messageListRef,
    },
    actions: {
      copyToClipboard,
      handleAuthSubmit,
      handleDraftChange,
      handleDraftKeyDown,
      handleMessageListScroll,
      handleModeChange,
      handleModelChange,
      handleSubmit,
      loadChatSession,
      scrollMessageListToBottom,
      sendMessage,
      setAuthEmail,
      setAuthError,
      setAuthMode,
      setAuthPassword,
      setActiveHtmlPreviewMessageId,
      setIsDraftEditorOpen,
      setOpenPicker,
      signOut,
      startNewChat,
      stopStreaming,
      toggleMessageExpansion,
      toggleTheme,
    },
  };
}
