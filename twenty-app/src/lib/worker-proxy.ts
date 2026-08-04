/**
 * Shared fetch wrapper used by every worker-*-proxy.ts logic function
 * (Phase 8). Centralizes base-URL resolution, the optional X-Api-Key
 * header, and error normalization so each thin proxy route file only has
 * to declare *which* worker path it forwards to -- not re-implement fetch
 * error handling four times over.
 *
 * `CONVERSATION_WORKER_BASE_URL` and `CRM_SYNC_WORKER_API_KEY` are the same
 * two serverVariables declared in application.config.ts -- the base URL is
 * reused from the existing Conversation Intelligence wiring rather than
 * adding a second "where is the worker" variable, and the API key is
 * optional (see worker/.env.example's WORKER_API_KEY -- both sides default
 * to unset/open).
 */

export class WorkerProxyError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export const callWorker = async <T = unknown>(
  method: 'GET' | 'POST',
  path: string,
): Promise<T> => {
  const baseUrl = process.env.CONVERSATION_WORKER_BASE_URL;
  if (!baseUrl) {
    throw new WorkerProxyError(
      503,
      'CONVERSATION_WORKER_BASE_URL is not configured on this app -- set it under the app\'s server variables.',
    );
  }

  const apiKey = process.env.CRM_SYNC_WORKER_API_KEY;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (apiKey) {
    headers['X-Api-Key'] = apiKey;
  }

  let response: globalThis.Response;
  try {
    response = await fetch(`${baseUrl.replace(/\/$/, '')}${path}`, { method, headers });
  } catch (error) {
    throw new WorkerProxyError(502, `Could not reach worker service: ${(error as Error).message}`);
  }

  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new WorkerProxyError(502, `Worker service returned non-JSON response: ${text.slice(0, 300)}`);
    }
  }

  if (!response.ok) {
    const detail =
      parsed && typeof parsed === 'object' && 'detail' in (parsed as Record<string, unknown>)
        ? String((parsed as Record<string, unknown>).detail)
        : text.slice(0, 300);
    throw new WorkerProxyError(response.status, detail || `Worker service returned ${response.status}`);
  }

  return parsed as T;
};
