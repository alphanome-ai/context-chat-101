import type { RefObject } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { HtmlPreview, Message } from "../lib/types";
import { extractHtmlPreview, isLongMessage } from "../lib/utils";

function formatTokenCount(value: number) {
  return value.toLocaleString();
}

type ChatMessagesProps = {
  activeHtmlPreview: HtmlPreview | null;
  copiedItemId: string | null;
  expandedMessageIds: Set<string>;
  messageListRef: RefObject<HTMLDivElement | null>;
  messages: Message[];
  onCopyMessage: (content: string, itemId: string) => void;
  onMessageListScroll: () => void;
  onToggleHtmlPreview: (messageId: string | null) => void;
  onToggleMessageExpansion: (messageId: string) => void;
};

export function ChatMessages({
  activeHtmlPreview,
  copiedItemId,
  expandedMessageIds,
  messageListRef,
  messages,
  onCopyMessage,
  onMessageListScroll,
  onToggleHtmlPreview,
  onToggleMessageExpansion,
}: ChatMessagesProps) {
  return (
    <div
      className="message-list"
      aria-live="polite"
      ref={messageListRef}
      onScroll={onMessageListScroll}
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
        const tokenUsage =
          message.role === "assistant" && !message.status
            ? message.tokenUsage
            : undefined;

        return (
          <article
            className={`message-bubble ${message.role} ${message.status ?? ""}`}
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
            {isCollapsibleMessage || canCopyMessage || tokenUsage ? (
              <div className="message-actions">
                {isCollapsibleMessage ? (
                  <button
                    className="response-toggle"
                    type="button"
                    aria-controls={messageContentId}
                    aria-expanded={isMessageExpanded}
                    onClick={() => onToggleMessageExpansion(message.id)}
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
                    onClick={() => onCopyMessage(message.content, copyItemId)}
                  >
                    <span className="copy-button-icon" aria-hidden="true" />
                    {isMessageCopied ? "Copied" : copyLabel}
                  </button>
                ) : null}
                {tokenUsage ? (
                  <details className="token-details">
                    <summary>
                      <span className="token-details-icon" aria-hidden="true" />
                      Token details
                    </summary>
                    <dl>
                      <div>
                        <dt>Prompt</dt>
                        <dd>{formatTokenCount(tokenUsage.promptTokens)}</dd>
                      </div>
                      <div>
                        <dt>Completion</dt>
                        <dd>{formatTokenCount(tokenUsage.completionTokens)}</dd>
                      </div>
                      <div>
                        <dt>Total</dt>
                        <dd>{formatTokenCount(tokenUsage.totalTokens)}</dd>
                      </div>
                    </dl>
                  </details>
                ) : null}
              </div>
            ) : null}
            {htmlPreview ? (
              <button
                className="html-preview-toggle"
                type="button"
                aria-pressed={isHtmlPreviewOpen}
                onClick={() =>
                  onToggleHtmlPreview(isHtmlPreviewOpen ? null : message.id)
                }
              >
                {isHtmlPreviewOpen ? "Close preview" : "Open HTML preview"}
              </button>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}
