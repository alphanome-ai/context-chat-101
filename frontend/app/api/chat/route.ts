import { fetchBackend } from "../_backend";

type ChatMessage = {
  role: "system" | "user" | "assistant" | "tool";
  content: string | null;
};

type ChatRequestBody = {
  messages?: ChatMessage[];
  model?: string;
  temperature?: number;
};

export async function POST(request: Request) {
  let body: ChatRequestBody;

  try {
    body = (await request.json()) as ChatRequestBody;
  } catch {
    return Response.json(
      { error: { message: "Invalid JSON request body." } },
      { status: 400 },
    );
  }

  if (!Array.isArray(body.messages) || body.messages.length === 0) {
    return Response.json(
      { error: { message: "At least one chat message is required." } },
      { status: 400 },
    );
  }

  const upstreamResponse = await fetchBackend("/api/v1/llm/inference/request", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: body.model ?? "default",
      messages: body.messages,
      stream: true,
      temperature: body.temperature ?? 0.2,
    }),
    cache: "no-store",
  });

  const contentType = upstreamResponse.headers.get("Content-Type") ?? "application/json";

  if (contentType.includes("text/event-stream")) {
    return new Response(upstreamResponse.body, {
      status: upstreamResponse.status,
      headers: {
        "Cache-Control": "no-cache",
        "Content-Type": contentType,
      },
    });
  }

  const responseBody = await upstreamResponse.text();

  return new Response(responseBody, {
    status: upstreamResponse.status,
    headers: {
      "Content-Type": contentType,
    },
  });
}
