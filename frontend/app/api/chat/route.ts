const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";

type ChatMessage = {
  role: "system" | "user" | "assistant" | "tool";
  content: string | null;
};

type ChatRequestBody = {
  messages?: ChatMessage[];
  model?: string;
  temperature?: number;
};

function getBackendUrl(pathname: string) {
  const baseUrl = process.env.BACKEND_API_URL ?? DEFAULT_BACKEND_URL;
  return new URL(pathname, baseUrl).toString();
}

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

  const upstreamResponse = await fetch(
    getBackendUrl("/api/v1/llm/chat/completion"),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: body.model ?? "default",
        messages: body.messages,
        stream: false,
        temperature: body.temperature ?? 0.2,
      }),
      cache: "no-store",
    },
  );

  const responseBody = await upstreamResponse.text();

  return new Response(responseBody, {
    status: upstreamResponse.status,
    headers: {
      "Content-Type":
        upstreamResponse.headers.get("Content-Type") ?? "application/json",
    },
  });
}
