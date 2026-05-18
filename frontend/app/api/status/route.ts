import { fetchBackend, proxyResponse } from "../_backend";

export async function GET() {
  const upstreamResponse = await fetchBackend("/api/v1/status", {
    cache: "no-store",
  });

  return proxyResponse(upstreamResponse);
}
