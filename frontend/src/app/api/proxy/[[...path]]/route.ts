import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";
const BACKEND_TIMEOUT_MS = 30_000;

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> }
) {
  return proxy(context.params, "GET", request);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> }
) {
  return proxy(context.params, "POST", request);
}

export async function PATCH(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> }
) {
  return proxy(context.params, "PATCH", request);
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> }
) {
  return proxy(context.params, "DELETE", request);
}

async function proxy(
  paramsPromise: Promise<{ path?: string[] }>,
  method: string,
  request?: NextRequest
) {
  const { path: pathSegments } = await paramsPromise;
  const path = pathSegments?.length ? `/${pathSegments.join("/")}` : "";
  const url = `${BACKEND_URL}${path}${request?.nextUrl.search ?? ""}`;

  const headers = new Headers();
  request?.headers.forEach((value, key) => {
    if (
      key.toLowerCase() !== "host" &&
      key.toLowerCase() !== "connection"
    ) {
      headers.set(key, value);
    }
  });

  let body: string | undefined;
  if (request?.body) {
    body = await request.text();
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), BACKEND_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(url, { method, headers, body, signal: controller.signal });
  } catch (err) {
    clearTimeout(timeoutId);
    const message =
      err instanceof Error && err.name === "AbortError"
        ? "Backend did not respond in time."
        : err instanceof Error
          ? err.message
          : "Could not reach backend.";
    return NextResponse.json(
      {
        detail: `${message} Ensure the backend is running (e.g. \`docker compose up -d backend\` or \`uvicorn app.main:app --port 8000\`).`,
      },
      { status: 502 }
    );
  }
  clearTimeout(timeoutId);
  const data = await res.text();
  const responseHeaders = new Headers();
  const contentType = res.headers.get("content-type");
  if (contentType) responseHeaders.set("content-type", contentType);
  return new NextResponse(data, {
    status: res.status,
    statusText: res.statusText,
    headers: responseHeaders,
  });
}
