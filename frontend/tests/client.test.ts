import { afterEach, describe, expect, it, vi } from "vitest";
import { request, isAppError, toAppError } from "@/lib/api/client";

const mockFetch = (impl: () => Promise<Response> | Response) => {
  vi.stubGlobal("fetch", vi.fn(impl));
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("API 客户端错误归一化", () => {
  it("后端错误结构 → AppError，带中文提示", async () => {
    mockFetch(() =>
      new Response(JSON.stringify({ error: { code: "OUTLINE_TOO_LONG", message: "字数超了" } }), {
        status: 400,
      }),
    );
    await expect(request("/api/x")).rejects.toMatchObject({
      code: "OUTLINE_TOO_LONG",
      userMessage: "大纲字数合计超过 18,000，请先删减",
      retryable: false,
    });
  });

  it("未知错误码用后端 message 兜底", async () => {
    mockFetch(() => new Response(JSON.stringify({ error: { code: "WEIRD", message: "后端说的话" } }), { status: 400 }));
    try {
      await request("/api/x");
      throw new Error("should throw");
    } catch (err) {
      expect(isAppError(err)).toBe(true);
      if (isAppError(err)) expect(err.userMessage).toBe("后端说的话");
    }
  });

  it("网络失败 → NETWORK_ERROR 且可重试", async () => {
    mockFetch(() => Promise.reject(new Error("offline")));
    await expect(request("/api/x")).rejects.toMatchObject({ code: "NETWORK_ERROR", retryable: true });
  });

  it("5xx 标记为可重试", () => {
    expect(toAppError("MODEL_FAILED", "挂了", 502).retryable).toBe(true);
    expect(toAppError("INVALID_REQUEST", "参数不对", 422).retryable).toBe(false);
  });

  it("JSON 请求自动带 Content-Type", async () => {
    let seen: Headers | undefined;
    vi.stubGlobal("fetch", async (_url: string, init: RequestInit) => {
      seen = new Headers(init.headers);
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    });
    await request("/api/reports", { method: "POST", json: { title: "x" } });
    expect(seen?.get("content-type")).toBe("application/json");
  });
});
