import { fetchBackend, getAuthHeaders } from "../_backend";

type Agent0RequestBody = {
  message?: string;
  model?: string;
  temperature?: number;
};

export async function POST(request: Request) {
  let body: Agent0RequestBody;

  try {
    body = (await request.json()) as Agent0RequestBody;
  } catch {
    return Response.json(
      { error: { message: "Invalid JSON request body." } },
      { status: 400 },
    );
  }

  const message = body.message?.trim();

  if (!message) {
    return Response.json(
      { error: { message: "An agent0 message is required." } },
      { status: 400 },
    );
  }

  const upstreamResponse = await fetchBackend("/api/v1/agent0/run", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(request),
    },
    body: JSON.stringify({
      model: body.model ?? "default",
      messages: [{ role: "user", content: message }],
      stream: true,
      temperature: body.temperature ?? 0.2,
    }),
    cache: "no-store",
    signal: request.signal,
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
