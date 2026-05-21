"use client";

import { AuthPanel } from "./chat/components/AuthPanel";
import { ChatMessages } from "./chat/components/ChatMessages";
import { Composer } from "./chat/components/Composer";
import { HistorySidebar } from "./chat/components/HistorySidebar";
import { HtmlPreviewPanel } from "./chat/components/HtmlPreviewPanel";
import { HydrationStage } from "./chat/components/HydrationStage";
import { Topbar } from "./chat/components/Topbar";
import { starterPrompts } from "./chat/lib/constants";
import { useChatController } from "./chat/useChatController";

export default function Home() {
  const { actions, refs, state } = useChatController();

  if (!state.isHydrated) {
    return <HydrationStage theme={state.theme} />;
  }

  return (
    <main className="chat-shell" data-theme={state.theme}>
      <Topbar
        currentUser={state.currentUser}
        isAuthenticated={state.isAuthenticated}
        isDarkMode={state.isDarkMode}
        providerLabel={state.providerLabel}
        providerStatus={state.providerStatus}
        onNewChat={actions.startNewChat}
        onSignOut={actions.signOut}
        onToggleTheme={actions.toggleTheme}
      />

      {!state.isAuthenticated ? (
        <AuthPanel
          authEmail={state.authEmail}
          authError={state.authError}
          authMode={state.authMode}
          authPassword={state.authPassword}
          isAuthLoading={state.isAuthLoading}
          onClearError={() => actions.setAuthError("")}
          onEmailChange={actions.setAuthEmail}
          onModeChange={actions.setAuthMode}
          onPasswordChange={actions.setAuthPassword}
          onSubmit={actions.handleAuthSubmit}
        />
      ) : (
        <div
          className={`chat-workspace ${
            state.activeHtmlPreview ? "with-preview" : ""
          }`}
        >
          <HistorySidebar
            activeSessionId={state.activeSessionId}
            chatSessions={state.chatSessions}
            historyError={state.historyError}
            isHistoryLoading={state.isHistoryLoading}
            onLoadSession={actions.loadChatSession}
          />

          <section
            className={
              state.hasMessages ? "chat-stage with-messages" : "chat-stage"
            }
          >
            {!state.hasMessages ? (
              <div className="empty-state">
                <h1>Hey!</h1>
                <div className="starter-list" aria-label="Starter messages">
                  {starterPrompts.map((prompt) => (
                    <button
                      className="starter-chip"
                      key={prompt}
                      type="button"
                      onClick={() => actions.sendMessage(prompt)}
                      disabled={state.isSending}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <ChatMessages
                activeHtmlPreview={state.activeHtmlPreview}
                copiedItemId={state.copiedItemId}
                expandedMessageIds={state.expandedMessageIds}
                messageListRef={refs.messageListRef}
                messages={state.messages}
                onCopyMessage={actions.copyToClipboard}
                onMessageListScroll={actions.handleMessageListScroll}
                onToggleHtmlPreview={actions.setActiveHtmlPreviewMessageId}
                onToggleMessageExpansion={actions.toggleMessageExpansion}
              />
            )}

            {state.hasMessages && state.showScrollToBottom ? (
              <button
                className="scroll-bottom-button"
                type="button"
                aria-label="Go to latest message"
                onClick={actions.scrollMessageListToBottom}
              >
                <span aria-hidden="true" />
              </button>
            ) : null}

            <Composer
              canSend={state.canSend}
              composerRef={refs.composerRef}
              draft={state.draft}
              draftInputRef={refs.draftInputRef}
              expandedDraftInputRef={refs.expandedDraftInputRef}
              isDraftEditorOpen={state.isDraftEditorOpen}
              isModelPickerDisabled={state.isModelPickerDisabled}
              isSending={state.isSending}
              llmOptions={state.llmOptions}
              openPicker={state.openPicker}
              selectedMode={state.selectedMode}
              selectedModeLabel={state.selectedModeLabel}
              selectedModel={state.selectedModel}
              selectedModelLabel={state.selectedModelLabel}
              sessionTokenUsage={state.sessionTokenUsage}
              onDraftChange={actions.handleDraftChange}
              onDraftKeyDown={actions.handleDraftKeyDown}
              onModeChange={actions.handleModeChange}
              onModelChange={actions.handleModelChange}
              onOpenDraftEditorChange={actions.setIsDraftEditorOpen}
              onOpenPickerChange={actions.setOpenPicker}
              onSendMessage={actions.sendMessage}
              onSubmit={actions.handleSubmit}
            />
          </section>

          {state.activeHtmlPreview ? (
            <HtmlPreviewPanel
              copiedItemId={state.copiedItemId}
              preview={state.activeHtmlPreview}
              onClose={() => actions.setActiveHtmlPreviewMessageId(null)}
              onCopySource={actions.copyToClipboard}
            />
          ) : null}
        </div>
      )}
    </main>
  );
}
