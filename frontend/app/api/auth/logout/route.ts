import { fetchBackend, getAuthHeaders, proxyResponse } from "../../_backend";

export async function POST(request: Request) {
  const upstreamResponse = await fetchBackend("/api/v1/auth/logout", {
    method: "POST",
    headers: getAuthHeaders(request),
    cache: "no-store",
  });

  return proxyResponse(upstreamResponse);
}
