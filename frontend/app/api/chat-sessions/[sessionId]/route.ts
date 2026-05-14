import { getAuthHeaders, getBackendUrl, proxyResponse } from "../../_backend";

type RouteContext = {
  params: Promise<{
    sessionId: string;
  }>;
};

export async function GET(request: Request, context: RouteContext) {
  const { sessionId } = await context.params;
  const upstreamResponse = await fetch(
    getBackendUrl(`/api/v1/chat-sessions/${sessionId}`),
    {
      headers: getAuthHeaders(request),
      cache: "no-store",
    },
  );

  return proxyResponse(upstreamResponse);
}

export async function DELETE(request: Request, context: RouteContext) {
  const { sessionId } = await context.params;
  const upstreamResponse = await fetch(
    getBackendUrl(`/api/v1/chat-sessions/${sessionId}`),
    {
      method: "DELETE",
      headers: getAuthHeaders(request),
      cache: "no-store",
    },
  );

  return proxyResponse(upstreamResponse);
}
