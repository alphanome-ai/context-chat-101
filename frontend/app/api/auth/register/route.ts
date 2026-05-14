import { getBackendUrl, proxyResponse } from "../../_backend";

export async function POST(request: Request) {
  const upstreamResponse = await fetch(getBackendUrl("/api/v1/auth/register"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
    cache: "no-store",
  });

  return proxyResponse(upstreamResponse);
}
