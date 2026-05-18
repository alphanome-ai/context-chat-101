"use client";

import {
  FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { z } from "zod";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  status?: "pending" | "streaming" | "error";
};

type HtmlPreview = {
  messageId: string;
  html: string;
};

type ApiMessage = {
  role: "user" | "assistant";
  content: string;
};

type ProviderStatus = "checking" | "online" | "offline";
type Theme = "light" | "dark";
type AuthMode = "login" | "register";
type ChatMode = "chat";
type PickerMenu = "mode" | "model";

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
  displayName: z.string().nullable().optional(),
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

const chatCompletionChunkSchema = z.object({
  choices: z
    .array(
      z.object({
        delta: assistantResponseMessageSchema.optional(),
      }),
    )
    .optional(),
  error: z.object({ message: z.string().optional() }).optional(),
});

const chatSessionSummarySchema = z.object({
  id: z.number(),
  title: z.string(),
  model: z.string().nullable().optional(),
  created_at: z.string(),
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
type AssistantStreamChunk = z.infer<typeof chatCompletionChunkSchema>;
type User = z.infer<typeof userSchema>;
type AuthResponse = z.infer<typeof errorResponseSchema>;
type ChatSessionSummary = z.infer<typeof chatSessionSummarySchema>;

const starterPrompts = [
  "Tell me a story?",
  "How does a space station work?",
  "Tell me I am awesome, dude, please.",
];

const AUTH_TOKEN_KEY = "context-chat-token";
const COLLAPSIBLE_MESSAGE_CHAR_LIMIT = 900;
const COLLAPSIBLE_MESSAGE_LINE_LIMIT = 14;
const DRAFT_EDITOR_AUTO_OPEN_CHAR_LIMIT = 180;
const DRAFT_EDITOR_AUTO_OPEN_LINE_LIMIT = 3;
const MESSAGE_LIST_BOTTOM_THRESHOLD = 80;
const PROVIDER_STATUS_POLL_INTERVAL_MS = 30_000;
const chatModeOptions: Array<{ id: ChatMode; label: string }> = [
  { id: "chat", label: "Chat" },
];

function createMessageId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function isLongMessage(content: string) {
  const trimmedContent = content.trim();
  const lineCount = trimmedContent.split(/\r\n|\r|\n/).length;

  return (
    trimmedContent.length > COLLAPSIBLE_MESSAGE_CHAR_LIMIT ||
    lineCount > COLLAPSIBLE_MESSAGE_LINE_LIMIT
  );
}

function shouldOpenDraftEditor(content: string) {
  return (
    content.length > DRAFT_EDITOR_AUTO_OPEN_CHAR_LIMIT ||
    content.split(/\r\n|\r|\n/).length >= DRAFT_EDITOR_AUTO_OPEN_LINE_LIMIT
  );
}

function isMessageListNearBottom(element: HTMLDivElement) {
  return (
    element.scrollHeight - element.scrollTop - element.clientHeight <=
    MESSAGE_LIST_BOTTOM_THRESHOLD
  );
}

async function writeClipboardText(text: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.setAttribute("readonly", "");
  textArea.style.position = "fixed";
  textArea.style.top = "-999px";
  textArea.style.left = "-999px";
  document.body.appendChild(textArea);
  textArea.select();
  document.execCommand("copy");
  document.body.removeChild(textArea);
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

async function readJsonResponse(response: Response): Promise<unknown> {
  const responseBody = await response.text();

  if (!responseBody.trim()) {
    return {};
  }

  try {
    return JSON.parse(responseBody) as unknown;
  } catch {
    return {
      error: {
        message: responseBody,
      },
    };
  }
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

function extractAssistantChunk(chunk: AssistantStreamChunk) {
  let content = "";
  let thinking = "";

  for (const choice of chunk.choices ?? []) {
    const delta = choice.delta;
    if (!delta) {
      continue;
    }

    content += delta.content ?? "";
    thinking += getThinkingText(delta) ?? "";
  }

  return { content, thinking };
}

async function readStreamingAssistantResponse(
  response: Response,
  onUpdate: (message: { content: string; thinking?: string }) => void,
) {
  if (!response.body) {
    throw new Error("The backend did not return a response stream.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let rawContent = "";
  let rawThinking = "";
  let isDone = false;

  function applyContentUpdate() {
    const { content, thinking: taggedThinking } = splitTaggedThinking(rawContent);
    const thinking = [rawThinking.trim(), taggedThinking].filter(Boolean).join("\n\n");

    onUpdate({
      content: content || (thinking ? "" : "Thinking"),
      thinking: thinking || undefined,
    });
  }

  function processFrame(frame: string) {
    const data = frame
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n")
      .trim();

    if (!data) {
      return;
    }

    if (data === "[DONE]") {
      isDone = true;
      return;
    }

    const parsed: unknown = JSON.parse(data);
    const chunk = chatCompletionChunkSchema.parse(parsed);

    if (chunk.error?.message) {
      throw new Error(chunk.error.message);
    }

    const nextDelta = extractAssistantChunk(chunk);
    if (!nextDelta.content && !nextDelta.thinking) {
      return;
    }

    rawContent += nextDelta.content;
    rawThinking += nextDelta.thinking;
    applyContentUpdate();
  }

  while (!isDone) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });

    let boundaryIndex = buffer.indexOf("\n\n");
    while (boundaryIndex !== -1) {
      const frame = buffer.slice(0, boundaryIndex);
      buffer = buffer.slice(boundaryIndex + 2);
      processFrame(frame);
      boundaryIndex = buffer.indexOf("\n\n");
    }

    if (done) {
      if (buffer.trim()) {
        processFrame(buffer);
      }
      break;
    }
  }

  const { content, thinking: taggedThinking } = splitTaggedThinking(rawContent);
  const thinking = [rawThinking.trim(), taggedThinking].filter(Boolean).join("\n\n");

  return {
    content: content.trim(),
    thinking: thinking || undefined,
  };
}

function getUtcTimestampValue(timestamp: string) {
  const trimmedTimestamp = timestamp.trim();
  const hasTimezone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(trimmedTimestamp);

  return hasTimezone ? trimmedTimestamp : `${trimmedTimestamp}Z`;
}

function formatLocalHistoryTimestamp(timestamp: string) {
  const date = new Date(getUtcTimestampValue(timestamp));

  if (Number.isNaN(date.getTime())) {
    return "Unknown time";
  }

  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(date);
}

function extractHtmlPreview(content: string, messageId: string): HtmlPreview | null {
  const htmlBlockPattern = /```(?:html|htm)\s*\n([\s\S]*?)```/gi;
  let match: RegExpExecArray | null;
  let html = "";

  while ((match = htmlBlockPattern.exec(content)) !== null) {
    html = match[1]?.trim() ?? "";
  }

  return html ? { messageId, html } : null;
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
  const [providerLabel, setProviderLabel] = useState("Checking backend");
  const [providerStatus, setProviderStatus] =
    useState<ProviderStatus>("checking");
  const [llmOptions, setLlmOptions] = useState<LlmOption[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [selectedMode, setSelectedMode] = useState<ChatMode>("chat");
  const [openPicker, setOpenPicker] = useState<PickerMenu | null>(null);
  const [activeHtmlPreviewMessageId, setActiveHtmlPreviewMessageId] =
    useState<string | null>(null);
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

  const canSend = draft.trim().length > 0 && !isSending;
  const hasMessages = messages.length > 0;
  const isDarkMode = theme === "dark";
  const isAuthenticated = Boolean(currentUser && authToken);
  const selectedModeLabel =
    chatModeOptions.find((option) => option.id === selectedMode)?.label ?? "Chat";
  const selectedModelOption = llmOptions.find((option) => option.id === selectedModel);
  const selectedModelLabel = selectedModelOption
    ? selectedModelOption.label
    : "LLM unavailable";
  const isModelPickerDisabled = isSending || llmOptions.length === 0;
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
      const rawData = await readJsonResponse(response);

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
      const rawData = await readJsonResponse(response);

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
    const rawData = await readJsonResponse(response);

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

    isMessageListAtBottomRef.current = true;
    setShowScrollToBottom(false);
    setMessages((current) => [...current, userMessage, pendingMessage]);
    setDraft("");
    setIsDraftEditorOpen(false);
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
      const contentType = response.headers.get("Content-Type") ?? "";

      if (!response.ok) {
        const rawData = await readJsonResponse(response);
        throw new Error(
          getApiErrorMessage(
            parseErrorResponse(rawData),
            "The backend returned an error.",
          ),
        );
      }

      let assistantContent = "";
      let thinking = "";

      if (contentType.includes("text/event-stream")) {
        const streamedMessage = await readStreamingAssistantResponse(
          response,
          (nextMessage) => {
            setMessages((current) =>
              current.map((message) =>
                message.id === pendingMessage.id
                  ? {
                      ...message,
                      content: nextMessage.content,
                      thinking: nextMessage.thinking,
                      status: "streaming",
                    }
                  : message,
              ),
            );
          },
        );

        assistantContent = streamedMessage.content;
        thinking = streamedMessage.thinking ?? "";
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

  function toggleResponseExpansion(messageId: string) {
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
      setActiveHtmlPreviewMessageId(null);
      setExpandedMessageIds(new Set());
      setCopiedItemId(null);
      setIsDraftEditorOpen(false);
      isMessageListAtBottomRef.current = true;
      setShowScrollToBottom(false);
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
      const rawData = await readJsonResponse(response);

      if (!response.ok) {
        throw new Error(
          getApiErrorMessage(parseErrorResponse(rawData), "Could not load this chat."),
        );
      }

      const data = storedChatSessionSchema.parse(rawData);
      setActiveSessionId(data.id);
      setActiveHtmlPreviewMessageId(null);
      setExpandedMessageIds(new Set());
      setCopiedItemId(null);
      setIsDraftEditorOpen(false);
      isMessageListAtBottomRef.current = true;
      setShowScrollToBottom(false);
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
    setActiveHtmlPreviewMessageId(null);
    setExpandedMessageIds(new Set());
    setCopiedItemId(null);
    setIsDraftEditorOpen(false);
    isMessageListAtBottomRef.current = true;
    setShowScrollToBottom(false);
    setDraft("");
  }

  function handleModelChange(modelId: string) {
    setSelectedModel(modelId);
    setOpenPicker(null);
  }

  function handleModeChange(mode: ChatMode) {
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
    setActiveHtmlPreviewMessageId(null);
    setExpandedMessageIds(new Set());
    setCopiedItemId(null);
    setIsDraftEditorOpen(false);
    isMessageListAtBottomRef.current = true;
    setShowScrollToBottom(false);
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
        <div className={`chat-workspace ${activeHtmlPreview ? "with-preview" : ""}`}>
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
              <div
                className="message-list"
                aria-live="polite"
                ref={messageListRef}
                onScroll={handleMessageListScroll}
              >
                {messages.map((message) => {
                  const htmlPreview =
                    message.role === "assistant" && !message.status
                      ? extractHtmlPreview(message.content, message.id)
                      : null;
                  const isHtmlPreviewOpen =
                    activeHtmlPreview?.messageId === message.id;
                  const isCollapsibleMessage =
                    !message.status && isLongMessage(message.content);
                  const isMessageExpanded = expandedMessageIds.has(message.id);
                  const isMessageCollapsed =
                    isCollapsibleMessage && !isMessageExpanded;
                  const messageContentId = `message-content-${message.id}`;
                  const copyItemId = `message-${message.id}`;
                  const copyLabel =
                    message.role === "assistant" ? "Copy response" : "Copy prompt";
                  const canCopyMessage =
                    message.role === "user" ||
                    (message.role === "assistant" && !message.status);
                  const isMessageCopied = copiedItemId === copyItemId;

                  return (
                    <article
                      className={`message-bubble ${message.role} ${
                        message.status ?? ""
                      }`}
                      key={message.id}
                    >
                      {message.status === "pending" ? (
                        <div className="thinking-loader" aria-label="Assistant is thinking">
                          <span className="thinking-loader-dots" aria-hidden="true">
                            <span />
                            <span />
                            <span />
                          </span>
                          <span>{message.content}</span>
                        </div>
                      ) : null}
                      {message.role === "assistant" && message.thinking ? (
                        <details className="thinking-panel">
                          <summary>Thinking</summary>
                          <div className="thinking-content markdown-preview">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {message.thinking}
                            </ReactMarkdown>
                          </div>
                        </details>
                      ) : null}
                      {message.status !== "pending" ? (
                        <div
                          id={messageContentId}
                          className={`message-text ${
                            message.role === "assistant" && !message.status
                              ? "markdown-preview"
                              : "plain-text"
                          } ${isMessageCollapsed ? "collapsed" : ""}`}
                        >
                          {message.role === "assistant" && !message.status ? (
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {message.content}
                            </ReactMarkdown>
                          ) : (
                            <>
                              {message.content}
                              {message.status === "streaming" ? (
                                <span className="streaming-cursor" aria-hidden="true" />
                              ) : null}
                            </>
                          )}
                        </div>
                      ) : null}
                      {isCollapsibleMessage || canCopyMessage ? (
                        <div className="message-actions">
                          {isCollapsibleMessage ? (
                            <button
                              className="response-toggle"
                              type="button"
                              aria-controls={messageContentId}
                              aria-expanded={isMessageExpanded}
                              onClick={() => toggleResponseExpansion(message.id)}
                            >
                              <span className="response-toggle-icon" aria-hidden="true" />
                              {isMessageExpanded
                                ? message.role === "assistant"
                                  ? "Minimize response"
                                  : "Minimize prompt"
                                : message.role === "assistant"
                                  ? "Show full response"
                                  : "Show full prompt"}
                            </button>
                          ) : null}
                          {canCopyMessage ? (
                            <button
                              className="copy-button"
                              type="button"
                              onClick={() =>
                                void copyToClipboard(message.content, copyItemId)
                              }
                            >
                              <span className="copy-button-icon" aria-hidden="true" />
                              {isMessageCopied ? "Copied" : copyLabel}
                            </button>
                          ) : null}
                        </div>
                      ) : null}
                      {htmlPreview ? (
                        <button
                          className="html-preview-toggle"
                          type="button"
                          aria-pressed={isHtmlPreviewOpen}
                          onClick={() =>
                            setActiveHtmlPreviewMessageId(
                              isHtmlPreviewOpen ? null : message.id,
                            )
                          }
                        >
                          {isHtmlPreviewOpen ? "Close preview" : "Open HTML preview"}
                        </button>
                      ) : null}
                    </article>
                  );
                })}
              </div>
            )}

            {hasMessages && showScrollToBottom ? (
              <button
                className="scroll-bottom-button"
                type="button"
                aria-label="Go to latest message"
                onClick={scrollMessageListToBottom}
              >
                <span aria-hidden="true" />
              </button>
            ) : null}

            <div className="composer-wrap">
              {isDraftEditorOpen ? (
                <div className="draft-editor-panel">
                  <div className="draft-editor-header">
                    <span>Message</span>
                    <button
                      className="draft-editor-close"
                      type="button"
                      onClick={() => setIsDraftEditorOpen(false)}
                    >
                      Collapse
                    </button>
                  </div>
                  <textarea
                    aria-label="Expanded message"
                    className="draft-editor-input"
                    ref={expandedDraftInputRef}
                    value={draft}
                    onChange={(event) => handleDraftChange(event.target.value)}
                    disabled={isSending}
                  />
                  <div className="draft-editor-footer">
                    <span>{draft.trim().length} characters</span>
                    <button
                      className="draft-editor-send"
                      type="button"
                      onClick={() => sendMessage(draft.trim())}
                      disabled={!canSend}
                    >
                      Send
                    </button>
                  </div>
                </div>
              ) : null}
              <form className="composer" onSubmit={handleSubmit} ref={composerRef}>
                <div className="mode-picker picker">
                <button
                  className="picker-trigger"
                  type="button"
                  aria-label="Chat mode"
                  aria-haspopup="listbox"
                  aria-expanded={openPicker === "mode"}
                  aria-controls="chat-mode-menu"
                  onClick={() =>
                    setOpenPicker((current) =>
                      current === "mode" ? null : "mode",
                    )
                  }
                  disabled={isSending}
                >
                  <span className="picker-trigger-text">
                    <span className="picker-label">Mode</span>
                    <span className="picker-value">{selectedModeLabel}</span>
                  </span>
                  <span className="picker-chevron" aria-hidden="true" />
                </button>
                {openPicker === "mode" ? (
                  <div
                    className="picker-menu"
                    id="chat-mode-menu"
                    role="listbox"
                    aria-label="Chat mode"
                  >
                    {chatModeOptions.map((option) => (
                      <button
                        className={
                          option.id === selectedMode
                            ? "picker-option selected"
                            : "picker-option"
                        }
                        key={option.id}
                        type="button"
                        role="option"
                        aria-selected={option.id === selectedMode}
                        onClick={() => handleModeChange(option.id)}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
              <div className="model-picker picker">
                <button
                  className="picker-trigger"
                  type="button"
                  aria-label="LLM model"
                  aria-haspopup="listbox"
                  aria-expanded={openPicker === "model"}
                  aria-controls="llm-model-menu"
                  onClick={() =>
                    setOpenPicker((current) =>
                      current === "model" ? null : "model",
                    )
                  }
                  disabled={isModelPickerDisabled}
                >
                  <span className="picker-trigger-text">
                    <span className="picker-label">Model</span>
                    <span className="picker-value">{selectedModelLabel}</span>
                  </span>
                  <span className="picker-chevron" aria-hidden="true" />
                </button>
                {openPicker === "model" ? (
                  <div
                    className="picker-menu model-menu"
                    id="llm-model-menu"
                    role="listbox"
                    aria-label="LLM model"
                  >
                    {llmOptions.map((option) => (
                      <button
                        className={
                          option.id === selectedModel
                            ? "picker-option selected"
                            : "picker-option"
                        }
                        key={`${option.providerName}-${option.id}`}
                        type="button"
                        role="option"
                        aria-selected={option.id === selectedModel}
                        onClick={() => handleModelChange(option.id)}
                      >
                        <span>{option.label}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
                <textarea
                  aria-label="Message"
                  placeholder="Type a Message"
                  ref={draftInputRef}
                  rows={1}
                  value={draft}
                  onChange={(event) => handleDraftChange(event.target.value)}
                  onKeyDown={handleDraftKeyDown}
                  disabled={isSending}
                />
                <button
                  className="draft-expand-button"
                  type="button"
                  aria-label="Open large message editor"
                  aria-pressed={isDraftEditorOpen}
                  onClick={() => setIsDraftEditorOpen(true)}
                  disabled={isSending}
                >
                  <span aria-hidden="true" />
                </button>
                <button
                  className="send-button"
                  type="submit"
                  aria-label="Send message"
                  disabled={!canSend}
                >
                  <span aria-hidden="true" className="arrow-up" />
                </button>
              </form>
            </div>
          </section>
          {activeHtmlPreview ? (
            <aside className="html-preview-panel" aria-label="HTML preview">
              <div className="html-preview-header">
                <div>
                  <span>HTML preview</span>
                  <small>Rendered output and source</small>
                </div>
                <button
                  className="html-preview-close"
                  type="button"
                  onClick={() => setActiveHtmlPreviewMessageId(null)}
                >
                  Close
                </button>
              </div>
              <div className="html-preview-body">
                <section className="html-preview-frame-section" aria-label="Rendered HTML">
                  <iframe
                    className="html-preview-frame"
                    title="Rendered HTML preview"
                    sandbox=""
                    srcDoc={activeHtmlPreview.html}
                  />
                </section>
                <section className="html-preview-source-section" aria-label="HTML source">
                  <div className="html-preview-section-title">
                    <span>Source</span>
                    <button
                      className="copy-button compact"
                      type="button"
                      onClick={() =>
                        void copyToClipboard(
                          activeHtmlPreview.html,
                          "html-preview-source",
                        )
                      }
                    >
                      <span className="copy-button-icon" aria-hidden="true" />
                      {copiedItemId === "html-preview-source" ? "Copied" : "Copy source"}
                    </button>
                  </div>
                  <pre>
                    <code>{activeHtmlPreview.html}</code>
                  </pre>
                </section>
              </div>
            </aside>
          ) : null}
        </div>
      )}
    </main>
  );
}
