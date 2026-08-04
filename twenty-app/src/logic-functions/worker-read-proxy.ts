import { defineLogicFunction, type RoutePayload } from 'twenty-sdk/define';
import { Response } from 'twenty-sdk/logic-function';

import { WORKER_READ_PROXY_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';
import { callWorker, WorkerProxyError } from 'src/lib/worker-proxy';

/**
 * Single generic GET proxy for every record-scoped worker read the Phase 8
 * front components need, rather than one near-identical logic-function
 * file per read (company-insights-panel.front-component.tsx,
 * research-tab.front-component.tsx, and conversation-panel.front-component.tsx
 * all call this one route with a different `resource`).
 *
 * `resource` is checked against an explicit allowlist below -- this is
 * NOT a general-purpose "forward any path" proxy. The worker's own base
 * URL is fixed server-side config (not attacker-controlled), so the risk
 * here isn't SSRF so much as accidentally exposing a worker endpoint this
 * app never meant to expose to the browser; the allowlist keeps that
 * explicit and auditable in one place.
 *
 * `isAuthRequired: true` means Twenty only invokes this handler for an
 * authenticated user session -- the primary access control for this route.
 * `WORKER_API_KEY`/`CRM_SYNC_WORKER_API_KEY` (see worker-proxy.ts) is
 * defense-in-depth on top of that for the worker-service leg.
 */

const RESOURCE_PATHS: Record<string, (recordId: string) => string> = {
  'company-insights': (id) => `/companies/${id}/insights`,
  'company-research-jobs': (id) => `/companies/${id}/research-jobs`,
  'company-enrichment-jobs': (id) => `/companies/${id}/enrichment-jobs`,
  'company-workflow': (id) => `/companies/${id}/workflow`,
  'person-conversation-signals': (id) => `/people/${id}/conversation-signals`,
};

const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const handler = async (event: RoutePayload): Promise<Response> => {
  const resource = event.pathParameters?.resource;
  const recordId = event.pathParameters?.recordId;

  if (!resource || !recordId) {
    return jsonResponse({ error: 'Missing resource or recordId path parameter' }, 400);
  }

  const buildPath = RESOURCE_PATHS[resource];
  if (!buildPath) {
    return jsonResponse({ error: `Unknown resource "${resource}"` }, 404);
  }

  try {
    const data = await callWorker('GET', buildPath(recordId));
    return jsonResponse(data, 200);
  } catch (error) {
    if (error instanceof WorkerProxyError) {
      return jsonResponse({ error: error.message }, error.status);
    }
    return jsonResponse({ error: (error as Error).message }, 500);
  }
};

export default defineLogicFunction({
  universalIdentifier: WORKER_READ_PROXY_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER,
  name: 'worker-read-proxy',
  timeoutSeconds: 15,
  handler,
  httpRouteTriggerSettings: {
    path: '/worker-read/:resource/:recordId',
    httpMethod: 'GET',
    isAuthRequired: true,
  },
});
