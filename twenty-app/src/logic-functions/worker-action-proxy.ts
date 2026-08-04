import { defineLogicFunction, type RoutePayload } from 'twenty-sdk/define';
import { Response } from 'twenty-sdk/logic-function';

import { WORKER_ACTION_PROXY_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';
import { callWorker, WorkerProxyError } from 'src/lib/worker-proxy';

/**
 * POST counterpart to worker-read-proxy.ts -- backs the "Enrich now" and
 * "Advance workflow" buttons in ai-insights-panel.front-component.tsx and
 * research-tab.front-component.tsx. Same allowlist-by-`action` pattern and
 * same `isAuthRequired: true` primary access control.
 *
 * Deliberately narrow: only two actions exist because only two things in
 * this codebase are safe to trigger on demand from a button click --
 * enrichment (a website crawl, idempotent, writes an audit record) and
 * workflow advance (which itself just calls enrichment today -- see
 * worker/scrapegraph_worker/workflow/engine.py). Nothing here can send an
 * email, message a prospect, or modify CRM data beyond what enrichment
 * already writes -- there is no outbound-messaging action to expose
 * because Phase 6 doesn't exist yet.
 */

const ACTION_PATHS: Record<string, (recordId: string) => string> = {
  enrich: (companyId) => `/companies/${companyId}/enrich`,
  'workflow-advance': (companyId) => `/companies/${companyId}/workflow/advance`,
};

const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const handler = async (event: RoutePayload): Promise<Response> => {
  const action = event.pathParameters?.action;
  const recordId = event.pathParameters?.recordId;

  if (!action || !recordId) {
    return jsonResponse({ error: 'Missing action or recordId path parameter' }, 400);
  }

  const buildPath = ACTION_PATHS[action];
  if (!buildPath) {
    return jsonResponse({ error: `Unknown action "${action}"` }, 404);
  }

  try {
    const data = await callWorker('POST', buildPath(recordId));
    return jsonResponse(data, 200);
  } catch (error) {
    if (error instanceof WorkerProxyError) {
      return jsonResponse({ error: error.message }, error.status);
    }
    return jsonResponse({ error: (error as Error).message }, 500);
  }
};

export default defineLogicFunction({
  universalIdentifier: WORKER_ACTION_PROXY_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER,
  name: 'worker-action-proxy',
  timeoutSeconds: 30, // enrichment does a live website crawl -- a little more headroom than the read proxies
  handler,
  httpRouteTriggerSettings: {
    path: '/worker-action/:action/:recordId',
    httpMethod: 'POST',
    isAuthRequired: true,
  },
});
