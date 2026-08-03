import { defineLogicFunction, type RoutePayload } from 'twenty-sdk/define';
import { Response } from 'twenty-sdk/logic-function';
import { CoreApiClient } from 'twenty-client-sdk/core';

import { CONVERSATION_SIGNAL_WEBHOOK_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';

/**
 * Receives the analysis result POSTed by the worker service once it has run
 * a reply through the LLM (see
 * worker/scrapegraph_worker/conversation/analyzer.py and
 * worker/scrapegraph_worker/conversation/twenty_push.py::push_conversation_signal_to_twenty).
 * Creates one ConversationSignal record and updates the denormalized
 * "latest" fields on the Person so list views don't need to join.
 *
 * Body shape sent by the worker:
 *   { personId, messageId, status, interestLevel, urgency, sentiment,
 *     objections, recommendedNextAction, recommendedReplyDraft,
 *     recommendedFollowUpAt, confidence, rawExcerpt, modelUsed, errorMessage }
 */

type SignalPayload = {
  personId: string;
  messageId?: string | null;
  status: 'COMPLETED' | 'FAILED';
  interestLevel?: string | null;
  urgency?: string | null;
  sentiment?: string | null;
  objections?: string | null;
  recommendedNextAction?: string | null;
  recommendedReplyDraft?: string | null;
  recommendedFollowUpAt?: string | null;
  confidence?: number | null;
  rawExcerpt?: string | null;
  modelUsed?: string | null;
  errorMessage?: string | null;
};

const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const handler = async (event: RoutePayload): Promise<Response> => {
  // Same shared-secret pattern as job-progress-webhook.ts -- the caller is
  // the worker service, not a logged-in Twenty user, so it's checked
  // manually against the raw header rather than via isAuthRequired.
  const authHeader = event.headers?.authorization ?? event.headers?.Authorization;
  const expected = `Bearer ${process.env.SCRAPE_WORKER_WEBHOOK_SHARED_SECRET ?? ''}`;
  if (!authHeader || authHeader !== expected) {
    return jsonResponse({ success: false, error: 'Unauthorized' }, 401);
  }

  const body = event.body as Partial<SignalPayload> | null;
  if (!body?.personId) {
    return jsonResponse({ success: false, error: 'Missing personId' }, 400);
  }

  const api = new CoreApiClient();

  const signal = await api.conversationSignals.create({
    status: body.status ?? 'FAILED',
    interestLevel: body.interestLevel ?? 'NONE',
    urgency: body.urgency ?? 'LOW',
    sentiment: body.sentiment ?? 'NEUTRAL',
    objections: body.objections ?? null,
    recommendedNextAction: body.recommendedNextAction ?? 'NO_ACTION',
    recommendedReplyDraft: body.recommendedReplyDraft ?? null,
    recommendedFollowUpAt: body.recommendedFollowUpAt ?? null,
    confidence: typeof body.confidence === 'number' ? Math.min(1, Math.max(0, body.confidence)) : 0,
    sourceMessageId: body.messageId ?? null,
    rawExcerpt: body.rawExcerpt ?? null,
    modelUsed: body.modelUsed ?? null,
    errorMessage: body.errorMessage ?? null,
    person: { id: body.personId },
  });

  // Best-effort denormalization onto Person -- a failure here shouldn't
  // undo the ConversationSignal write, which is the source of truth.
  if (body.status === 'COMPLETED') {
    try {
      await api.people.update(body.personId, {
        latestInterestLevel: body.interestLevel ?? 'NONE',
        latestUrgency: body.urgency ?? 'LOW',
        lastConversationSignalAt: new Date().toISOString(),
      });
    } catch {
      // Logged nowhere yet -- see this file's README section on
      // observability once a logging sink is wired up for this app.
    }
  }

  return jsonResponse({ success: true, conversationSignalId: signal.id });
};

export default defineLogicFunction({
  universalIdentifier: CONVERSATION_SIGNAL_WEBHOOK_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER,
  name: 'conversation-signal-webhook',
  timeoutSeconds: 15,
  handler,
  httpRouteTriggerSettings: {
    path: '/conversation-signal',
    httpMethod: 'POST',
    isAuthRequired: false, // auth is enforced manually above via the shared secret
  },
});
