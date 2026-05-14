import { getAuthHeaders, getBackendUrl, proxyResponse } from "../../_backend";

export async function GET(request: Request) {
  const upstreamResponse = await fetch(getBackendUrl("/api/v1/auth/me"), {
    headers: getAuthHeaders(request),
    cache: "no-store",
  });

  return proxyResponse(upstreamResponse);
}
