import { fetchBackend, getAuthHeaders } from "../_backend";

type Agent1RequestBody = {
  message?: string;
  session_id?: string | null;
};

export async function POST(request: Request) {
  let body: Agent1RequestBody;

  try {
    body = (await request.json()) as Agent1RequestBody;
  } catch {
    return Response.json(
      { error: { message: "Invalid JSON request body." } },
      { status: 400 },
    );
  }

  const message = body.message?.trim();

  if (!message) {
    return Response.json(
      { error: { message: "An agent1 message is required." } },
      { status: 400 },
    );
  }

  const upstreamResponse = await fetchBackend("/api/v1/agent1/run", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(request),
    },
    body: JSON.stringify({
      session_id: body.session_id ?? undefined,
      message,
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
