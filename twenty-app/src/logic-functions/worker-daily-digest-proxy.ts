import { defineLogicFunction, type RoutePayload } from 'twenty-sdk/define';
import { Response } from 'twenty-sdk/logic-function';

import { WORKER_DAILY_DIGEST_PROXY_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';
import { callWorker, WorkerProxyError } from 'src/lib/worker-proxy';

/**
 * Kept as its own route rather than folded into worker-read-proxy.ts's
 * `:resource/:recordId` pattern because the daily digest isn't scoped to
 * any record -- there's no id to put in the path. Backs
 * recommendations-widget.front-component.tsx.
 */

const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const handler = async (_event: RoutePayload): Promise<Response> => {
  try {
    const data = await callWorker('GET', '/recommendations/daily-digest');
    return jsonResponse(data, 200);
  } catch (error) {
    if (error instanceof WorkerProxyError) {
      return jsonResponse({ error: error.message }, error.status);
    }
    return jsonResponse({ error: (error as Error).message }, 500);
  }
};

export default defineLogicFunction({
  universalIdentifier: WORKER_DAILY_DIGEST_PROXY_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER,
  name: 'worker-daily-digest-proxy',
  timeoutSeconds: 15,
  handler,
  httpRouteTriggerSettings: {
    path: '/worker-daily-digest',
    httpMethod: 'GET',
    isAuthRequired: true,
  },
});
