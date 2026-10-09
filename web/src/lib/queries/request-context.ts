import {
  assertRequestContextCurrent,
  organizationRequestContext,
  type ApiRequestContext,
} from "../api";

export async function requestInContext<T>(
  context: ApiRequestContext,
  request: () => Promise<T>,
): Promise<T> {
  assertRequestContextCurrent(context);
  const result = await request();
  assertRequestContextCurrent(context);
  return result;
}

export function requiredOrganizationContext(organizationId: number | null): ApiRequestContext {
  if (organizationId === null) {
    throw new Error("An organization context is required for this request");
  }
  return organizationRequestContext(organizationId);
}
