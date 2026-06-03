import { fetchBackend, getAuthHeaders } from "../_backend";

type ChatRequestBody = {
  session_id?: string | null;
  message?: string;
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

  const message = body.message?.trim();

  if (!message) {
    return Response.json(
      { error: { message: "A chat message is required." } },
      { status: 400 },
    );
  }

  const upstreamResponse = await fetchBackend("/api/v1/chat/run", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(request),
    },
    body: JSON.stringify({
      session_id: body.session_id ?? null,
      model: body.model ?? "default",
      message,
      stream: true,
      stream_options: {
        include_usage: true,
      },
      temperature: body.temperature ?? 0.2,
    }),
    cache: "no-store",
    signal: request.signal,
  });

  const contentType =
    upstreamResponse.headers.get("Content-Type") ?? "application/json";

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
