import { getAuthHeaders, getBackendUrl, proxyResponse } from "../../../_backend";

type RouteContext = {
  params: Promise<{
    sessionId: string;
  }>;
};

export async function POST(request: Request, context: RouteContext) {
  const { sessionId } = await context.params;
  const upstreamResponse = await fetch(
    getBackendUrl(`/api/v1/chat-sessions/${sessionId}/messages`),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(request),
      },
      body: await request.text(),
      cache: "no-store",
    },
  );

  return proxyResponse(upstreamResponse);
}
