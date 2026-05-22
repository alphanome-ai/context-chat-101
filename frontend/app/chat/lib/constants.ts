import type { ChatMode } from "./types";

export const starterPrompts = [
  "Tell me a story?",
  "How does a space station work?",
  "Tell me I am awesome, dude, please.",
];

export const AUTH_TOKEN_KEY = "context-chat-token";
export const COLLAPSIBLE_MESSAGE_CHAR_LIMIT = 900;
export const COLLAPSIBLE_MESSAGE_LINE_LIMIT = 14;
export const DRAFT_EDITOR_AUTO_OPEN_CHAR_LIMIT = 180;
export const DRAFT_EDITOR_AUTO_OPEN_LINE_LIMIT = 3;
export const MESSAGE_LIST_BOTTOM_THRESHOLD = 80;
export const PROVIDER_STATUS_POLL_INTERVAL_MS = 30_000;

export const chatModeOptions: Array<{ id: ChatMode; label: string }> = [
  { id: "chat", label: "Chat" },
  { id: "agent0", label: "Agent0" },
];
