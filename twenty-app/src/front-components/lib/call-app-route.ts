/**
 * Shared fetch helper for calling this app's own HTTP routes
 * (worker-read-proxy.ts / worker-daily-digest-proxy.ts / worker-action-proxy.ts)
 * from front components.
 *
 * ASSUMPTION FLAGGED FOR VERIFICATION: front components run inside Twenty's
 * UI via a sandboxed Remote DOM Web Worker (see worker/README.md's
 * front-component notes / docs.twenty.com's Apps overview). I could not
 * find documented guidance -- nor verify against a live workspace, since
 * this sandbox has no running Twenty instance -- on the exact convention
 * for a front component calling *its own app's* HTTP routes specifically
 * (as opposed to Twenty's Core API, which goes through the documented
 * `CoreApiClient`). `APP_ROUTE_BASE_PATH` below is my best inference from
 * this repo's own existing convention for this app's routes (see
 * worker/README.md's mention of `.../s/crm-sync/job-progress`), assuming a
 * plain relative `fetch()` resolves against the hosting page's origin the
 * same way it would in a normal same-origin browser context. If a real
 * install shows a different base path (check the Network tab after
 * clicking into one of the Phase 8 tabs), update the constant below --
 * every front component in this app goes through this one function, so
 * that's the only place a fix would be needed.
 */

const APP_ROUTE_BASE_PATH = '/s/crm-sync';

export class AppRouteError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export const callAppRoute = async <T = unknown>(method: 'GET' | 'POST', path: string): Promise<T> => {
  let response: Response;
  try {
    const baseUrl = "http://localhost:2020";
    response = await fetch(`${baseUrl}${APP_ROUTE_BASE_PATH}${path}`, {
    method,
});
  } catch (error) {
    throw new AppRouteError(0, `Network error calling ${path}: ${(error as Error).message}`);
  }

  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new AppRouteError(response.status, `Non-JSON response from ${path}: ${text.slice(0, 200)}`);
    }
  }

  if (!response.ok) {
    const message =
      parsed && typeof parsed === 'object' && 'error' in (parsed as Record<string, unknown>)
        ? String((parsed as Record<string, unknown>).error)
        : `Request to ${path} failed with ${response.status}`;
    throw new AppRouteError(response.status, message);
  }

  return parsed as T;
};
