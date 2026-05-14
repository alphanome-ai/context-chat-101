export function getBackendUrl(pathname: string) {
  const baseUrl = process.env.BACKEND_API_URL;

  if (!baseUrl) {
    throw new Error("BACKEND_API_URL is not configured in frontend/.env");
  }

  return new URL(pathname, baseUrl).toString();
}

export function getAuthHeaders(request: Request): Record<string, string> {
  const authorization = request.headers.get("Authorization");
  return authorization ? { Authorization: authorization } : {};
}

export async function proxyResponse(upstreamResponse: Response) {
  const responseBody = await upstreamResponse.text();

  return new Response(responseBody, {
    status: upstreamResponse.status,
    headers: {
      "Content-Type":
        upstreamResponse.headers.get("Content-Type") ?? "application/json",
    },
  });
}
