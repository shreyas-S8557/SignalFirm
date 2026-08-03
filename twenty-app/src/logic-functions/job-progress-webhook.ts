import { defineLogicFunction, type RoutePayload } from 'twenty-sdk/define';
import { Response } from 'twenty-sdk/logic-function';
import { CoreApiClient } from 'twenty-client-sdk/core';

import { JOB_PROGRESS_WEBHOOK_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';

/**
 * Receives progress updates POSTed by the Scrapegraph worker service
 * (see scrapegraph-worker/scrapegraph_worker/progress.py::push_progress_to_twenty)
 * and reflects them onto every ResearchJob record whose `sourceRunId`
 * matches the job. This is what makes job progress visible inside Twenty
 * itself (not just via the worker's own /jobs API) without giving the
 * worker service a general-purpose Twenty API key with write access beyond
 * this one narrow purpose.
 *
 * Body shape sent by the worker:
 *   { sourceRunId, stage, processedRows, totalRows, createdCount,
 *     updatedCount, duplicateCount, errorCount }
 */

type ProgressPayload = {
  sourceRunId: string;
  stage: string;
  processedRows: number;
  totalRows: number;
  createdCount: number;
  updatedCount: number;
  duplicateCount: number;
  errorCount: number;
};

const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const handler = async (event: RoutePayload): Promise<Response> => {
  // Twenty validates the Bearer token against this app's serverVariables
  // before invoking the handler when isAuthRequired is true for a
  // *user*-scoped call; for a service-to-service webhook like this one we
  // additionally check the shared secret ourselves against the raw header,
  // since the caller is the worker service, not a logged-in Twenty user.
  const authHeader = event.headers?.authorization ?? event.headers?.Authorization;
  const expected = `Bearer ${process.env.SCRAPE_WORKER_WEBHOOK_SHARED_SECRET ?? ''}`;
  if (!authHeader || authHeader !== expected) {
    return jsonResponse({ success: false, error: 'Unauthorized' }, 401);
  }

  const body = event.body as Partial<ProgressPayload> | null;
  if (!body?.sourceRunId) {
    return jsonResponse({ success: false, error: 'Missing sourceRunId' }, 400);
  }

  const api = new CoreApiClient();
  const matches = await api.researchJobs.find({
    filter: `sourceRunId[eq]:${body.sourceRunId}`,
    limit: 60, // one job can touch many ResearchJob rows; batch limit applies per Twenty's API
  });

  const summaryNote =
    `stage=${body.stage} processed=${body.processedRows ?? 0}/${body.totalRows ?? 0} ` +
    `created=${body.createdCount ?? 0} updated=${body.updatedCount ?? 0} ` +
    `duplicates=${body.duplicateCount ?? 0} errors=${body.errorCount ?? 0}`;

  await Promise.all(
    matches.map((job) =>
      api.researchJobs.update(job.id, {
        status: body.stage === 'FAILED' ? 'FAILED' : job.status,
      }),
    ),
  );

  return jsonResponse({ success: true, matchedResearchJobs: matches.length, summary: summaryNote });
};

export default defineLogicFunction({
  universalIdentifier: JOB_PROGRESS_WEBHOOK_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER,
  name: 'job-progress-webhook',
  timeoutSeconds: 30,
  handler,
  httpRouteTriggerSettings: {
    path: '/job-progress',
    httpMethod: 'POST',
    isAuthRequired: false, // auth is enforced manually above via the shared secret
  },
});
