import { getBackendUrl } from "../_backend";

export async function GET() {
  const upstreamResponse = await fetch(getBackendUrl("/api/v1/llm/providers"), {
    cache: "no-store",
  });
  const responseBody = await upstreamResponse.text();

  return new Response(responseBody, {
    status: upstreamResponse.status,
    headers: {
      "Content-Type":
        upstreamResponse.headers.get("Content-Type") ?? "application/json",
    },
  });
}
