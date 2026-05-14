import { getAuthHeaders, getBackendUrl, proxyResponse } from "../../_backend";

export async function POST(request: Request) {
  const upstreamResponse = await fetch(getBackendUrl("/api/v1/auth/logout"), {
    method: "POST",
    headers: getAuthHeaders(request),
    cache: "no-store",
  });

  return proxyResponse(upstreamResponse);
}
