import { fetchBackend, getAuthHeaders, proxyResponse } from "../../_backend";

export async function GET(request: Request) {
  const upstreamResponse = await fetchBackend("/api/v1/auth/me", {
    headers: getAuthHeaders(request),
    cache: "no-store",
  });

  return proxyResponse(upstreamResponse);
}
