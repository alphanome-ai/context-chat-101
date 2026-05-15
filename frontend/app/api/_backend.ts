export function getBackendUrl(pathname: string) {
  const baseUrl = process.env.BACKEND_API_URL;

  if (!baseUrl) {
    throw new Error("BACKEND_API_URL is not configured in frontend/.env");
  }

  return new URL(pathname, baseUrl).toString();
}

export async function fetchBackend(pathname: string, init?: RequestInit) {
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => timeoutController.abort(), 15_000);

  try {
    return await fetch(getBackendUrl(pathname), {
      ...init,
      signal: init?.signal ?? timeoutController.signal,
    });
  } catch {
    return Response.json(
      {
        error: {
          message: "Could not connect to the Backend. Try again later.",
        },
      },
      { status: 503 },
    );
  } finally {
    clearTimeout(timeoutId);
  }
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
