const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";

function getBackendUrl(pathname: string) {
  const baseUrl = process.env.BACKEND_API_URL ?? DEFAULT_BACKEND_URL;
  return new URL(pathname, baseUrl).toString();
}

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
