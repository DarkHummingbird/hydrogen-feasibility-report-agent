/**
 * 同源代理：把浏览器的 /api/* 在请求时转发到后端（手册 12.5）。
 *
 * - 目标地址运行时读取 BACKEND_URL，换后端不用重新构建；
 * - 原样带回状态码、响应体与 Set-Cookie，避免跨域；
 * - 没配 BACKEND_URL 时返回 503 统一错误结构。
 * 本次不上线（D13），所以不写 x-client-ip / PROXY_SHARED_SECRET（见《前端适配声明》§6）。
 */
import { NextRequest, NextResponse } from "next/server";

export const config = {
  matcher: "/api/:path*",
};

const backendBase = () => (process.env.BACKEND_URL || "").replace(/\/$/, "");

export default async function proxy(request: NextRequest): Promise<NextResponse> {
  const base = backendBase();
  if (!base) {
    return NextResponse.json(
      { error: { code: "BACKEND_NOT_CONFIGURED", message: "没有配置后端地址（BACKEND_URL）" } },
      { status: 503 },
    );
  }

  const url = new URL(request.url);
  const target = `${base}${url.pathname}${url.search}`;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");

  let body: ArrayBuffer | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    body = await request.arrayBuffer();
  }

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      redirect: "manual",
      cache: "no-store",
    });

    const responseHeaders = new Headers(upstream.headers);
    responseHeaders.delete("content-encoding");
    responseHeaders.delete("content-length");
    responseHeaders.delete("transfer-encoding");

    return new NextResponse(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json(
      { error: { code: "BACKEND_UNREACHABLE", message: "后端没有启动或网络不通，请确认后端已在运行" } },
      { status: 502 },
    );
  }
}
