const DEFAULT_API_URL = "http://localhost:8000";

/** Base URL of the FastAPI backend, without a trailing slash. */
export function apiBaseUrl(value: string | undefined = process.env.NEXT_PUBLIC_API_URL): string {
  const url = value?.trim() || DEFAULT_API_URL;
  return url.replace(/\/+$/, "");
}
