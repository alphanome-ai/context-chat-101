import { fetchBackend, proxyResponse } from "../../_backend";

export async function POST(request: Request) {
  const upstreamResponse = await fetchBackend("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
    cache: "no-store",
  });

  return proxyResponse(upstreamResponse);
}
