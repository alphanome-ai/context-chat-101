import type { z } from "zod";

import type {
  chatSessionSummarySchema,
  errorResponseSchema,
  userSchema,
} from "./schemas";

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  tokenUsage?: TokenUsage;
  status?: "pending" | "streaming" | "error";
};

export type TokenUsage = {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
};

export type HtmlPreview = {
  messageId: string;
  html: string;
};

export type ProviderStatus = "checking" | "online" | "offline";
export type Theme = "light" | "dark";
export type AuthMode = "login" | "register";
export type ChatMode = "chat" | "agent";
export type PickerMenu = "mode" | "model";

export type LlmOption = {
  id: string;
  label: string;
  providerName: string;
  isDefault?: boolean;
};

export type User = z.infer<typeof userSchema>;
export type AuthResponse = z.infer<typeof errorResponseSchema>;
export type ChatSessionSummary = z.infer<typeof chatSessionSummarySchema>;
