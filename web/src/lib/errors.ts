import { ApiError, RequestContextChangedError } from "./api";

export function errorMessage(error: unknown, t: (key: string) => string): string {
  if (error instanceof RequestContextChangedError) return t("common.contextChanged");
  if (error instanceof ApiError) return error.message;
  return t("common.requestFailed");
}
