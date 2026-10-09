export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly code: string | null = null,
    readonly requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Query = Record<string, string | number | boolean | undefined>;

export type ApiRequestContext =
  | { scope: "current" }
  | { scope: "instance" }
  | { scope: "organization"; organizationId: number };

export interface ApiRequestOptions {
  context?: ApiRequestContext;
  signal?: AbortSignal;
  /** Only OrgProvider's server-confirmed enter/exit handshake may intentionally
   * complete while local storage still contains the previous context. */
  allowContextTransition?: boolean;
}

export const currentRequestContext = { scope: "current" } as const satisfies ApiRequestContext;
export const instanceRequestContext = { scope: "instance" } as const satisfies ApiRequestContext;

export function organizationRequestContext(organizationId: number): ApiRequestContext {
  if (!Number.isSafeInteger(organizationId) || organizationId < 1) {
    throw new Error("organizationId must be a positive safe integer");
  }
  return { scope: "organization", organizationId };
}

export class RequestContextChangedError extends Error {
  constructor() {
    super("The active organization changed. Review the action and try again.");
    this.name = "RequestContextChangedError";
  }
}

// The organization the operator has "entered". Read from storage on every
// request so a superadmin's reads and writes target that org; ignored server-side
// for everyone else.
export const ACTING_ORG_STORAGE_KEY = "driftwatch_acting_org";

let sessionBinding: { id: number; organizationId: number | null; operator: boolean } | null = null;
let sessionRevision = 0;

/** Bind explicit organization requests to the server-confirmed signed-in user.
 * Acting-org storage is only an operator's requested context, never a member's
 * organization membership. No credentials are retained here. */
export function bindRequestSession(user: { id: number; organization_id: number | null; is_superadmin: boolean } | null): void {
  const next = user ? { id: user.id, organizationId: user.organization_id, operator: user.is_superadmin } : null;
  if (JSON.stringify(next) !== JSON.stringify(sessionBinding)) sessionRevision += 1;
  sessionBinding = next;
}

function storedActingOrganizationId(): number | null {
  try {
    const raw = localStorage.getItem(ACTING_ORG_STORAGE_KEY);
    if (!raw) return null;
    const id = (JSON.parse(raw) as { id?: number }).id;
    return typeof id === "number" && Number.isSafeInteger(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
}

export function isRequestContextCurrent(context: ApiRequestContext): boolean {
  if (context.scope === "current") return true;
  const current = storedActingOrganizationId();
  if (context.scope === "organization" && sessionBinding && !sessionBinding.operator) {
    return sessionBinding.organizationId === context.organizationId && (current === null || current === context.organizationId);
  }
  return context.scope === "instance" ? current === null : current === context.organizationId;
}

export function assertRequestContextCurrent(context: ApiRequestContext): void {
  if (!isRequestContextCurrent(context)) throw new RequestContextChangedError();
}

type ConcreteRequestContext = Exclude<ApiRequestContext, { scope: "current" }>;

function captureRequestContext(context: ApiRequestContext | undefined): ConcreteRequestContext {
  if (context?.scope === "instance" || context?.scope === "organization") return context;
  const organizationId = storedActingOrganizationId();
  return organizationId === null
    ? instanceRequestContext
    : { scope: "organization", organizationId };
}

function requestContextHeaders(context: ConcreteRequestContext): Record<string, string> {
  return context.scope === "organization"
    ? { "X-Acting-Org": String(context.organizationId) }
    : {};
}

function validateCompletedRequestContext(
  context: ConcreteRequestContext,
  options: ApiRequestOptions | undefined,
  revision: number,
): void {
  if (!options?.allowContextTransition) assertRequestContextCurrent(context);
  if (revision !== sessionRevision) throw new RequestContextChangedError();
}

function buildUrl(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  query?: Query,
  options?: ApiRequestOptions,
): Promise<T> {
  const context = captureRequestContext(options?.context);
  const revision = sessionRevision;
  const headers: Record<string, string> = { ...requestContextHeaders(context) };
  if (body !== undefined) headers["content-type"] = "application/json";
  const response = await fetch(buildUrl(path, query), {
    method,
    credentials: "include",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: options?.signal,
  });

  if (response.status === 204) {
    validateCompletedRequestContext(context, options, revision);
    return undefined as T;
  }

  if (!response.ok) {
    const error = await readError(response);
    validateCompletedRequestContext(context, options, revision);
    throw new ApiError(response.status, error.message, error.code, error.requestId);
  }
  const data = (await response.json()) as T;
  validateCompletedRequestContext(context, options, revision);
  return data;
}

async function download(path: string, filename: string, query?: Query): Promise<void> {
  const context = captureRequestContext(undefined);
  const revision = sessionRevision;
  const response = await fetch(buildUrl(path, query), {
    credentials: "include", headers: requestContextHeaders(context),
  });
  if (!response.ok) {
    const error = await readError(response);
    validateCompletedRequestContext(context, undefined, revision);
    throw new ApiError(response.status, error.message, error.code, error.requestId);
  }
  const blob = await response.blob();
  validateCompletedRequestContext(context, undefined, revision);
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function uploadRaw<T>(
  path: string,
  file: File,
  contentType = "application/octet-stream",
  options?: ApiRequestOptions,
): Promise<T> {
  const context = captureRequestContext(options?.context);
  const revision = sessionRevision;
  const response = await fetch(path, {
    method: "POST",
    credentials: "include",
    headers: {
      ...requestContextHeaders(context),
      "content-type": contentType || "application/octet-stream",
    },
    body: file,
    signal: options?.signal,
  });
  if (response.status === 204) {
    validateCompletedRequestContext(context, options, revision);
    return undefined as T;
  }
  if (!response.ok) {
    const error = await readError(response);
    validateCompletedRequestContext(context, options, revision);
    throw new ApiError(response.status, error.message, error.code, error.requestId);
  }
  const data = (await response.json()) as T;
  validateCompletedRequestContext(context, options, revision);
  return data;
}

type ParsedError = {
  message: string;
  code: string | null;
  requestId: string | null;
};

const ERROR_CODE_PATTERN = /^[a-z][a-z0-9_.-]{0,63}$/;
const REQUEST_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/;
const MAX_ERROR_MESSAGE_LENGTH = 1_000;

async function readError(response: Response): Promise<ParsedError> {
  const fallback = `Request failed (${response.status})`;
  const headerRequestId = safeIdentifier(
    response.headers.get("X-Request-ID"),
    REQUEST_ID_PATTERN,
  );
  try {
    const data: unknown = await response.json();
    if (!isRecord(data)) return { message: fallback, code: null, requestId: headerRequestId };

    const code = safeIdentifier(data.error_code, ERROR_CODE_PATTERN);
    const bodyRequestId = safeIdentifier(data.request_id, REQUEST_ID_PATTERN);
    return {
      message: detailMessage(data.detail) ?? fallback,
      code,
      requestId: headerRequestId ?? bodyRequestId,
    };
  } catch {
    // fall through to a generic message
  }
  return { message: fallback, code: null, requestId: headerRequestId };
}

function detailMessage(detail: unknown): string | null {
  const direct = safeMessage(detail);
  if (direct) return direct;
  if (!Array.isArray(detail)) return null;
  for (const item of detail) {
    if (!isRecord(item)) continue;
    const message = safeMessage(item.msg);
    if (message) return message;
  }
  return null;
}

function safeMessage(value: unknown): string | null {
  if (typeof value !== "string" || value.length === 0) return null;
  return value.slice(0, MAX_ERROR_MESSAGE_LENGTH);
}

function safeIdentifier(value: unknown, pattern: RegExp): string | null {
  return typeof value === "string" && pattern.test(value) ? value : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export const api = {
  download,
  get: <T>(path: string, query?: Query, options?: ApiRequestOptions) =>
    request<T>("GET", path, undefined, query, options),
  post: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>
    request<T>("POST", path, body, undefined, options),
  patch: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>
    request<T>("PATCH", path, body, undefined, options),
  put: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>
    request<T>("PUT", path, body, undefined, options),
  del: (path: string, options?: ApiRequestOptions) =>
    request<void>("DELETE", path, undefined, undefined, options),
  uploadRaw: <T>(
    path: string,
    file: File,
    contentType?: string,
    options?: ApiRequestOptions,
  ) => uploadRaw<T>(path, file, contentType, options),
};
