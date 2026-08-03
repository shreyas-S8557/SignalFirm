import { defineLogicFunction, type DatabaseEventPayload, type ObjectRecordCreateEvent } from 'twenty-sdk/define';
import { CoreApiClient } from 'twenty-client-sdk/core';

import { REPLY_INTELLIGENCE_TRIGGER_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';

/**
 * Fires on every new Message record (Twenty's own email-sync writes these
 * when a mailbox is connected -- see Settings -> Accounts). Most Message
 * creates are our own outbound sends, so this function has to actively
 * filter down to genuine inbound replies before doing anything expensive:
 *
 *   1. Skip drafts outright (`isDraft`).
 *   2. Look up the MessageChannelMessageAssociation for this message and
 *      skip unless `direction` is `INCOMING` -- this is what distinguishes
 *      "someone replied to us" from "we just sent an email".
 *   3. Resolve the sender to a Person via MessageParticipant (`role: from`).
 *      If the sender isn't linked to any Person record, there's nothing to
 *      attach a ConversationSignal to, so this is skipped rather than guessed.
 *
 * What survives that filter gets forwarded to the worker service's
 * `/conversation/analyze` endpoint (see
 * worker/scrapegraph_worker/conversation/), which runs the actual LLM
 * detection and recommendation, then calls back into
 * conversation-signal-webhook.ts with the result. This function does no LLM
 * work itself -- it's pure routing/filtering, same division of labor as the
 * rest of this app (see application.config.ts).
 */

type MessageRecord = {
  id: string;
  subject?: string | null;
  text?: string | null;
  receivedAt?: string | null;
  isDraft?: boolean | null;
  messageThread?: { id: string } | null;
};

type MessageChannelMessageAssociationRecord = {
  direction: 'INCOMING' | 'OUTGOING';
};

type MessageParticipantRecord = {
  role: string;
  person?: { id: string } | null;
};

const handler = async (event: DatabaseEventPayload<ObjectRecordCreateEvent<MessageRecord>>): Promise<void> => {
  const message = event.properties.after;

  if (!message?.id || message.isDraft) {
    return;
  }

  const workerBaseUrl = process.env.CONVERSATION_WORKER_BASE_URL;
  const sharedSecret = process.env.SCRAPE_WORKER_WEBHOOK_SHARED_SECRET;
  if (!workerBaseUrl || !sharedSecret) {
    // Not configured yet -- silently no-op rather than throwing, so email
    // sync keeps working normally before this module's env vars are set.
    return;
  }

  const api = new CoreApiClient();

  const associations = await api.messageChannelMessageAssociations.find({
    filter: `message.id[eq]:${message.id}`,
    limit: 1,
  });
  const direction = (associations[0] as MessageChannelMessageAssociationRecord | undefined)?.direction;
  if (direction !== 'INCOMING') {
    return;
  }

  const participants = await api.messageParticipants.find({
    filter: `message.id[eq]:${message.id},role[eq]:from`,
    limit: 1,
    depth: 1,
  });
  const sender = participants[0] as MessageParticipantRecord | undefined;
  const personId = sender?.person?.id;
  if (!personId) {
    // No Person on file for this sender address -- nothing to attach a
    // signal to. (A future milestone could auto-create a Person here.)
    return;
  }

  const excerpt = (message.text ?? '').slice(0, 4000);

  await fetch(`${workerBaseUrl.replace(/\/$/, '')}/conversation/analyze`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${sharedSecret}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      messageId: message.id,
      threadId: message.messageThread?.id ?? null,
      personId,
      subject: message.subject ?? null,
      text: excerpt,
      receivedAt: message.receivedAt ?? null,
    }),
  });
};

export default defineLogicFunction({
  universalIdentifier: REPLY_INTELLIGENCE_TRIGGER_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER,
  name: 'reply-intelligence-trigger',
  timeoutSeconds: 15,
  handler,
  databaseEventTriggerSettings: {
    eventName: 'messages.created',
  },
});
