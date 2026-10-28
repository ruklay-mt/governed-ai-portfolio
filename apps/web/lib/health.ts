export type ApiState = "unknown" | "warming" | "ready" | "unavailable";

/**
 * Wake the API (Cloud Run and Neon scale to zero) and report when it is ready.
 * Retries for up to ~45 s, which covers a cold start of both.
 */
export async function warmUp(
  baseUrl: string,
  onState: (state: ApiState) => void,
  fetcher: typeof fetch = fetch,
  attempts = 6,
  delayMs = 7000,
): Promise<ApiState> {
  onState("warming");
  for (let attempt = 0; attempt < attempts; attempt++) {
    try {
      const response = await fetcher(`${baseUrl}/api/health`, { cache: "no-store" });
      if (response.ok) {
        const body = (await response.json()) as { db?: string };
        if (body.db === "ok") {
          onState("ready");
          return "ready";
        }
      }
    } catch {
      // Cold start or network blip: try again.
    }
    if (attempt < attempts - 1) await new Promise((r) => setTimeout(r, delayMs));
  }
  onState("unavailable");
  return "unavailable";
}
