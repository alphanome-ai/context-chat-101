import { fetchBackend, getAuthHeaders, proxyResponse } from "../_backend";

export async function GET(request: Request) {
  const upstreamResponse = await fetchBackend("/api/v1/chat-sessions", {
    headers: getAuthHeaders(request),
    cache: "no-store",
  });

  return proxyResponse(upstreamResponse);
}

export async function POST(request: Request) {
  const upstreamResponse = await fetchBackend("/api/v1/chat-sessions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(request),
    },
    body: await request.text(),
    cache: "no-store",
  });

  return proxyResponse(upstreamResponse);
}
