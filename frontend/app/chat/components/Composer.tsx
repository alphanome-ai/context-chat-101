import type {
  FormEvent,
  KeyboardEvent as ReactKeyboardEvent,
  RefObject,
} from "react";

import { chatModeOptions } from "../lib/constants";
import type { ChatMode, LlmOption, PickerMenu, TokenUsage } from "../lib/types";

type ComposerProps = {
  canSend: boolean;
  composerRef: RefObject<HTMLFormElement | null>;
  draft: string;
  draftInputRef: RefObject<HTMLTextAreaElement | null>;
  expandedDraftInputRef: RefObject<HTMLTextAreaElement | null>;
  isDraftEditorOpen: boolean;
  isModelPickerDisabled: boolean;
  isSending: boolean;
  llmOptions: LlmOption[];
  openPicker: PickerMenu | null;
  selectedMode: ChatMode;
  selectedModeLabel: string;
  selectedModel: string;
  selectedModelLabel: string;
  sessionTokenUsage: TokenUsage;
  onDraftChange: (value: string) => void;
  onDraftKeyDown: (event: ReactKeyboardEvent<HTMLTextAreaElement>) => void;
  onModeChange: (mode: ChatMode) => void;
  onModelChange: (modelId: string) => void;
  onOpenDraftEditorChange: (isOpen: boolean) => void;
  onOpenPickerChange: (menu: PickerMenu | null) => void;
  onSendMessage: (content: string) => void;
  onStopStreaming: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export function Composer({
  canSend,
  composerRef,
  draft,
  draftInputRef,
  expandedDraftInputRef,
  isDraftEditorOpen,
  isModelPickerDisabled,
  isSending,
  llmOptions,
  openPicker,
  selectedMode,
  selectedModeLabel,
  selectedModel,
  selectedModelLabel,
  sessionTokenUsage,
  onDraftChange,
  onDraftKeyDown,
  onModeChange,
  onModelChange,
  onOpenDraftEditorChange,
  onOpenPickerChange,
  onSendMessage,
  onStopStreaming,
  onSubmit,
}: ComposerProps) {
  const hasSessionUsage = sessionTokenUsage.totalTokens > 0;

  return (
    <div className="composer-wrap">
      {hasSessionUsage ? (
        <div className="session-token-usage" aria-label="Session token usage">
          <span>Session tokens</span>
          <strong>{sessionTokenUsage.totalTokens.toLocaleString()}</strong>
          <small>
            {sessionTokenUsage.inputTokens.toLocaleString()} input /{" "}
            {sessionTokenUsage.outputTokens.toLocaleString()} output
          </small>
        </div>
      ) : null}
      {isDraftEditorOpen ? (
        <div className="draft-editor-panel">
          <div className="draft-editor-header">
            <span>Message</span>
            <button
              className="draft-editor-close"
              type="button"
              onClick={() => onOpenDraftEditorChange(false)}
            >
              Collapse
            </button>
          </div>
          <textarea
            aria-label="Expanded message"
            className="draft-editor-input"
            ref={expandedDraftInputRef}
            value={draft}
            onChange={(event) => onDraftChange(event.target.value)}
            disabled={isSending}
          />
          <div className="draft-editor-footer">
            <span>{draft.trim().length} characters</span>
            <button
              className="draft-editor-send"
              type="button"
              onClick={() => onSendMessage(draft.trim())}
              disabled={!canSend}
            >
              Send
            </button>
          </div>
        </div>
      ) : null}
      <form className="composer" onSubmit={onSubmit} ref={composerRef}>
        <div className="mode-picker picker">
          <button
            className="picker-trigger"
            type="button"
            aria-label="Chat mode"
            aria-haspopup="listbox"
            aria-expanded={openPicker === "mode"}
            aria-controls="chat-mode-menu"
            onClick={() =>
              onOpenPickerChange(openPicker === "mode" ? null : "mode")
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
                  onClick={() => onModeChange(option.id)}
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
              onOpenPickerChange(openPicker === "model" ? null : "model")
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
                  onClick={() => onModelChange(option.id)}
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
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={onDraftKeyDown}
          disabled={isSending}
        />
        <button
          className="draft-expand-button"
          type="button"
          aria-label="Open large message editor"
          aria-pressed={isDraftEditorOpen}
          onClick={() => onOpenDraftEditorChange(true)}
          disabled={isSending}
        >
          <span aria-hidden="true" />
        </button>
        {isSending ? (
          <button
            className="stop-button"
            type="button"
            aria-label="Stop streaming"
            title="Stop streaming"
            onClick={onStopStreaming}
          >
            <span aria-hidden="true" className="stop-icon" />
          </button>
        ) : (
          <button
            className="send-button"
            type="submit"
            aria-label="Send message"
            disabled={!canSend}
          >
            <span aria-hidden="true" className="arrow-up" />
          </button>
        )}
      </form>
    </div>
  );
}
