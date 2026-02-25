import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

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

  const res = await fetch(url, { method, headers, body });
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
