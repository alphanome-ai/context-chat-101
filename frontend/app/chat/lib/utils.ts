import { z } from "zod";

import {
  COLLAPSIBLE_MESSAGE_CHAR_LIMIT,
  COLLAPSIBLE_MESSAGE_LINE_LIMIT,
  DRAFT_EDITOR_AUTO_OPEN_CHAR_LIMIT,
  DRAFT_EDITOR_AUTO_OPEN_LINE_LIMIT,
  MESSAGE_LIST_BOTTOM_THRESHOLD,
} from "./constants";
import { errorResponseSchema } from "./schemas";
import type { HtmlPreview } from "./types";

export function createMessageId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function isLongMessage(content: string) {
  const trimmedContent = content.trim();
  const lineCount = trimmedContent.split(/\r\n|\r|\n/).length;

  return (
    trimmedContent.length > COLLAPSIBLE_MESSAGE_CHAR_LIMIT ||
    lineCount > COLLAPSIBLE_MESSAGE_LINE_LIMIT
  );
}

export function shouldOpenDraftEditor(content: string) {
  return (
    content.length > DRAFT_EDITOR_AUTO_OPEN_CHAR_LIMIT ||
    content.split(/\r\n|\r|\n/).length >= DRAFT_EDITOR_AUTO_OPEN_LINE_LIMIT
  );
}

export function isMessageListNearBottom(element: HTMLDivElement) {
  return (
    element.scrollHeight - element.scrollTop - element.clientHeight <=
    MESSAGE_LIST_BOTTOM_THRESHOLD
  );
}

export async function writeClipboardText(text: string) {
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

export function getErrorMessage(error: unknown) {
  if (error instanceof z.ZodError) {
    return (
      error.issues[0]?.message ??
      "The response did not match the expected shape."
    );
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "The assistant could not respond.";
}

export function getApiErrorMessage(payload: unknown, fallback: string) {
  const parsedPayload = errorResponseSchema.safeParse(payload).data ?? {};

  if (parsedPayload.error?.message) {
    return parsedPayload.error.message;
  }
  if (typeof parsedPayload.detail === "string") {
    return parsedPayload.detail;
  }
  return fallback;
}

export async function readJsonResponse(response: Response): Promise<unknown> {
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

export function getUtcTimestampValue(timestamp: string) {
  const trimmedTimestamp = timestamp.trim();
  const hasTimezone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(trimmedTimestamp);

  return hasTimezone ? trimmedTimestamp : `${trimmedTimestamp}Z`;
}

export function formatLocalHistoryTimestamp(timestamp: string) {
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

export function extractHtmlPreview(
  content: string,
  messageId: string,
): HtmlPreview | null {
  const htmlBlockPattern = /```(?:html|htm)\s*\n([\s\S]*?)```/gi;
  let match: RegExpExecArray | null;
  let html = "";

  while ((match = htmlBlockPattern.exec(content)) !== null) {
    html = match[1]?.trim() ?? "";
  }

  return html ? { messageId, html } : null;
}
