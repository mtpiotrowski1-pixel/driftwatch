import { QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ACTING_ORG_STORAGE_KEY,
  ApiError,
  RequestContextChangedError,
  api,
  bindRequestSession,
  instanceRequestContext,
  organizationRequestContext,
} from "./api";

function response(body: unknown, init: ResponseInit): Response {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
  });
}

async function capturedError(request: Promise<unknown>): Promise<ApiError> {
  try {
    await request;
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    return error as ApiError;
  }
  throw new Error("Expected request to reject");
}

describe("API error contract", () => {
  afterEach(() => {
    bindRequestSession(null);
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("accepts the ordinary admin's own organization without acting-org storage", async () => {
    bindRequestSession({ id: 1, organization_id: 22, is_superadmin: false });
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(response({ brand_name: "Tenant" }, { status: 200 }))));
    await expect(api.get("/api/settings", undefined, { context: organizationRequestContext(22) })).resolves.toEqual({ brand_name: "Tenant" });
    await expect(api.put("/api/settings", {}, { context: organizationRequestContext(22) })).resolves.toEqual({ brand_name: "Tenant" });
    await expect(api.get("/api/settings", undefined, { context: organizationRequestContext(23) })).rejects.toBeInstanceOf(RequestContextChangedError);
  });

  it("rejects a response from a previous user even when the organization id is unchanged", async () => {
    bindRequestSession({ id: 1, organization_id: 22, is_superadmin: false });
    let finish!: (value: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
    const pending = api.get("/api/sites");
    bindRequestSession({ id: 2, organization_id: 22, is_superadmin: false });
    finish(response([], { status: 200 }));
    await expect(pending).rejects.toBeInstanceOf(RequestContextChangedError);
  });

  it.each(["request error", "upload"])("discards a late %s after the signed-in user changes", async (kind) => {
    bindRequestSession({ id: 1, organization_id: 22, is_superadmin: false });
    let finish!: (value: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
    const pending = kind === "upload"
      ? api.uploadRaw("/api/branding/logo", new File(["asset"], "logo.png"))
      : api.get("/api/settings");
    bindRequestSession({ id: 2, organization_id: 22, is_superadmin: false });
    finish(response(kind === "upload" ? { url: "/asset" } : { detail: "Previous user's private error" }, { status: kind === "upload" ? 200 : 403 }));
    await expect(pending).rejects.toBeInstanceOf(RequestContextChangedError);
  });

  it("downloads with the selected organization and discards a late export after switching", async () => {
    localStorage.setItem(ACTING_ORG_STORAGE_KEY, JSON.stringify({ id: 4 }));
    let finish!: (value: Response) => void;
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    const pending = api.download("/api/exports/changes.xlsx", "changes.xlsx");
    localStorage.setItem(ACTING_ORG_STORAGE_KEY, JSON.stringify({ id: 9 }));
    finish(new Response("export rows", { status: 200 }));
    await expect(pending).rejects.toBeInstanceOf(RequestContextChangedError);
    expect(fetchMock).toHaveBeenCalledWith("/api/exports/changes.xlsx", expect.objectContaining({ headers: { "X-Acting-Org": "4" } }));
  });

  it("uses the explicitly bound organization header", async () => {
    localStorage.setItem(
      ACTING_ORG_STORAGE_KEY,
      JSON.stringify({ id: 9, name: "Bound org" }),
    );
    const fetchMock = vi.fn().mockResolvedValue(response({}, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await api.post(
      "/api/privileged",
      { enabled: true },
      { context: organizationRequestContext(9) },
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/privileged",
      expect.objectContaining({
        headers: expect.objectContaining({ "X-Acting-Org": "9" }),
      }),
    );
  });

  it("omits the acting organization for explicit instance requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({}, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await api.get("/api/instance", undefined, { context: instanceRequestContext });

    const options = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(options.headers).not.toHaveProperty("X-Acting-Org");
  });

  it("rejects an old tenant response before it can populate the new tenant cache", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const queryKey = ["tenant-resource"] as const;
    localStorage.setItem(
      ACTING_ORG_STORAGE_KEY,
      JSON.stringify({ id: 4, name: "Organization A" }),
    );
    let finish!: (value: Response) => void;
    const fetchMock = vi.fn().mockImplementation(
      () => new Promise<Response>((resolve) => {
        finish = resolve;
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const pending = client.fetchQuery({
      queryKey,
      queryFn: () => api.get<Array<{ id: number }>>("/api/tenant-resource"),
    });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    localStorage.setItem(
      ACTING_ORG_STORAGE_KEY,
      JSON.stringify({ id: 9, name: "Organization B" }),
    );
    finish(response([{ id: 41 }], { status: 200 }));

    await expect(pending).rejects.toBeInstanceOf(RequestContextChangedError);
    expect(client.getQueryData(queryKey)).toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/tenant-resource",
      expect.objectContaining({
        headers: expect.objectContaining({ "X-Acting-Org": "4" }),
      }),
    );
  });

  it("preserves message and exposes the stable code and correlation ID", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response(
          {
            detail: "Plan limit reached",
            error_code: "plan_limit_reached",
            request_id: "body-id",
          },
          { status: 403, headers: { "X-Request-ID": "trace-123" } },
        ),
      ),
    );

    const error = await capturedError(api.get("/api/sites"));

    expect(error.status).toBe(403);
    expect(error.message).toBe("Plan limit reached");
    expect(error.code).toBe("plan_limit_reached");
    expect(error.requestId).toBe("trace-123");
  });

  it("reads a validation message and falls back to the body request ID", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response(
          {
            detail: [{ type: "value_error", msg: "Invalid email" }],
            error_code: "validation_error",
            request_id: "validation.1",
          },
          { status: 422 },
        ),
      ),
    );

    const error = await capturedError(api.post("/api/auth/register", {}));

    expect(error.message).toBe("Invalid email");
    expect(error.code).toBe("validation_error");
    expect(error.requestId).toBe("validation.1");
  });

  it("rejects malformed metadata and safely handles non-JSON responses", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        response(
          {
            detail: { nested: "not user-facing" },
            error_code: "INVALID CODE",
            request_id: "../../unsafe",
          },
          { status: 502 },
        ),
      )
      .mockResolvedValueOnce(
        new Response("gateway failure", {
          status: 503,
          headers: { "X-Request-ID": "gateway-4" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const malformed = await capturedError(api.get("/api/first"));
    const nonJson = await capturedError(api.get("/api/second"));

    expect(malformed.message).toBe("Request failed (502)");
    expect(malformed.code).toBeNull();
    expect(malformed.requestId).toBeNull();
    expect(nonJson.message).toBe("Request failed (503)");
    expect(nonJson.code).toBeNull();
    expect(nonJson.requestId).toBe("gateway-4");
  });

  it("bounds server-provided messages before exposing them to the UI", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response(
          { detail: "x".repeat(5_000), error_code: "bad_request", request_id: "bounded-1" },
          { status: 400 },
        ),
      ),
    );

    const error = await capturedError(api.get("/api/large-error"));

    expect(error.message).toHaveLength(1_000);
    expect(error.code).toBe("bad_request");
    expect(error.requestId).toBe("bounded-1");
  });
});
