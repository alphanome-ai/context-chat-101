import {
  chatCompletionChunkSchema,
  type AssistantResponseMessage,
  type AssistantStreamChunk,
} from "./schemas";

export function getThinkingText(message?: AssistantResponseMessage) {
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

export function splitTaggedThinking(content: string) {
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

export async function readStreamingAssistantResponse(
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
    const { content, thinking: taggedThinking } =
      splitTaggedThinking(rawContent);
    const thinking = [rawThinking.trim(), taggedThinking]
      .filter(Boolean)
      .join("\n\n");

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

  const { content, thinking: taggedThinking } =
    splitTaggedThinking(rawContent);
  const thinking = [rawThinking.trim(), taggedThinking]
    .filter(Boolean)
    .join("\n\n");

  return {
    content: content.trim(),
    thinking: thinking || undefined,
  };
}
