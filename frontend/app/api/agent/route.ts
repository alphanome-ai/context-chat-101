import { fetchBackend } from "../_backend";

type ChatMessage = {
  role: "system" | "user" | "assistant" | "tool";
  content: string | null;
};

type AgentRequestBody = {
  messages?: ChatMessage[];
  model?: string;
  temperature?: number;
};

export async function POST(request: Request) {
  let body: AgentRequestBody;

  try {
    body = (await request.json()) as AgentRequestBody;
  } catch {
    return Response.json(
      { error: { message: "Invalid JSON request body." } },
      { status: 400 },
    );
  }

  if (!Array.isArray(body.messages) || body.messages.length === 0) {
    return Response.json(
      { error: { message: "At least one agent message is required." } },
      { status: 400 },
    );
  }

  const upstreamResponse = await fetchBackend("/api/v1/agent/run", {
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

  const responseBody = await upstreamResponse.text();

  return new Response(responseBody, {
    status: upstreamResponse.status,
    headers: {
      "Content-Type":
        upstreamResponse.headers.get("Content-Type") ?? "application/json",
    },
  });
}
