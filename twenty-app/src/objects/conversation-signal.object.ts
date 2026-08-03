import { defineObject, FieldType, ObjectOpenRecordIn } from 'twenty-sdk/define';

import {
  CONVERSATION_SIGNAL_OBJECT_UNIVERSAL_IDENTIFIER,
  CONVERSATION_SIGNAL_STATUS_FIELD_UNIVERSAL_IDENTIFIER,
  CONVERSATION_SIGNAL_INTEREST_LEVEL_FIELD_UNIVERSAL_IDENTIFIER,
  CONVERSATION_SIGNAL_URGENCY_FIELD_UNIVERSAL_IDENTIFIER,
  CONVERSATION_SIGNAL_SENTIMENT_FIELD_UNIVERSAL_IDENTIFIER,
  CONVERSATION_SIGNAL_OBJECTIONS_FIELD_UNIVERSAL_IDENTIFIER,
  CONVERSATION_SIGNAL_NEXT_ACTION_FIELD_UNIVERSAL_IDENTIFIER,
  CONVERSATION_SIGNAL_REPLY_DRAFT_FIELD_UNIVERSAL_IDENTIFIER,
  CONVERSATION_SIGNAL_FOLLOW_UP_AT_FIELD_UNIVERSAL_IDENTIFIER,
  CONVERSATION_SIGNAL_CONFIDENCE_FIELD_UNIVERSAL_IDENTIFIER,
  CONVERSATION_SIGNAL_SOURCE_MESSAGE_ID_FIELD_UNIVERSAL_IDENTIFIER,
  CONVERSATION_SIGNAL_RAW_EXCERPT_FIELD_UNIVERSAL_IDENTIFIER,
  CONVERSATION_SIGNAL_ERROR_FIELD_UNIVERSAL_IDENTIFIER,
  CONVERSATION_SIGNAL_MODEL_USED_FIELD_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

/**
 * One record per inbound reply the worker's Conversation Intelligence
 * module has analyzed (see worker/scrapegraph_worker/conversation/). Mirrors
 * the ICPScore/EnrichmentJob pattern: one row per analysis run rather than
 * overwriting in place, so a contact's signal history is preserved as they
 * reply multiple times over a deal's lifecycle.
 *
 * `interestLevel`/`urgency`/`sentiment` are LLM-derived classifications --
 * always constrained to a fixed enum by the worker before this record is
 * written (see conversation/analyzer.py), never freeform LLM text, so
 * downstream views/filters/automations can rely on them.
 */
enum ConversationSignalStatus {
  PENDING = 'PENDING',
  COMPLETED = 'COMPLETED',
  FAILED = 'FAILED',
}

enum InterestLevel {
  HIGH = 'HIGH',
  MEDIUM = 'MEDIUM',
  LOW = 'LOW',
  NONE = 'NONE',
}

enum Urgency {
  HIGH = 'HIGH',
  MEDIUM = 'MEDIUM',
  LOW = 'LOW',
}

enum Sentiment {
  POSITIVE = 'POSITIVE',
  NEUTRAL = 'NEUTRAL',
  NEGATIVE = 'NEGATIVE',
  MIXED = 'MIXED',
}

enum NextAction {
  SEND_REPLY = 'SEND_REPLY',
  SCHEDULE_FOLLOW_UP = 'SCHEDULE_FOLLOW_UP',
  ESCALATE_TO_HUMAN = 'ESCALATE_TO_HUMAN',
  MARK_WON = 'MARK_WON',
  MARK_LOST = 'MARK_LOST',
  NO_ACTION = 'NO_ACTION',
}

export default defineObject({
  universalIdentifier: CONVERSATION_SIGNAL_OBJECT_UNIVERSAL_IDENTIFIER,
  nameSingular: 'conversationSignal',
  namePlural: 'conversationSignals',
  labelSingular: 'Conversation Signal',
  labelPlural: 'Conversation Signals',
  description:
    'One AI analysis of an inbound reply: detected interest/objections/urgency/sentiment, ' +
    'plus a recommended reply, follow-up timing, and next action.',
  icon: 'IconMessageCircle2',
  openRecordIn: ObjectOpenRecordIn.SIDE_PANEL,
  fields: [
    {
      universalIdentifier: CONVERSATION_SIGNAL_STATUS_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'status',
      type: FieldType.SELECT,
      label: 'Status',
      icon: 'IconProgressCheck',
      defaultValue: `'${ConversationSignalStatus.PENDING}'`,
      options: [
        { value: ConversationSignalStatus.PENDING, label: 'Pending', position: 0, color: 'gray' },
        { value: ConversationSignalStatus.COMPLETED, label: 'Completed', position: 1, color: 'green' },
        { value: ConversationSignalStatus.FAILED, label: 'Failed', position: 2, color: 'red' },
      ],
    },
    {
      universalIdentifier: CONVERSATION_SIGNAL_INTEREST_LEVEL_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'interestLevel',
      type: FieldType.SELECT,
      label: 'Interest level',
      icon: 'IconFlame',
      defaultValue: `'${InterestLevel.NONE}'`,
      options: [
        { value: InterestLevel.HIGH, label: 'High', position: 0, color: 'green' },
        { value: InterestLevel.MEDIUM, label: 'Medium', position: 1, color: 'yellow' },
        { value: InterestLevel.LOW, label: 'Low', position: 2, color: 'orange' },
        { value: InterestLevel.NONE, label: 'None detected', position: 3, color: 'gray' },
      ],
    },
    {
      universalIdentifier: CONVERSATION_SIGNAL_URGENCY_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'urgency',
      type: FieldType.SELECT,
      label: 'Urgency',
      icon: 'IconAlarm',
      defaultValue: `'${Urgency.LOW}'`,
      options: [
        { value: Urgency.HIGH, label: 'High', position: 0, color: 'red' },
        { value: Urgency.MEDIUM, label: 'Medium', position: 1, color: 'yellow' },
        { value: Urgency.LOW, label: 'Low', position: 2, color: 'gray' },
      ],
    },
    {
      universalIdentifier: CONVERSATION_SIGNAL_SENTIMENT_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'sentiment',
      type: FieldType.SELECT,
      label: 'Sentiment',
      icon: 'IconMoodSmile',
      defaultValue: `'${Sentiment.NEUTRAL}'`,
      options: [
        { value: Sentiment.POSITIVE, label: 'Positive', position: 0, color: 'green' },
        { value: Sentiment.NEUTRAL, label: 'Neutral', position: 1, color: 'gray' },
        { value: Sentiment.NEGATIVE, label: 'Negative', position: 2, color: 'red' },
        { value: Sentiment.MIXED, label: 'Mixed', position: 3, color: 'yellow' },
      ],
    },
    {
      universalIdentifier: CONVERSATION_SIGNAL_OBJECTIONS_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'objections',
      type: FieldType.RICH_TEXT,
      label: 'Objections',
      icon: 'IconShieldExclamation',
      description: 'Bullet list of objections the model detected in the reply. Empty when none found.',
      isNullable: true,
    },
    {
      universalIdentifier: CONVERSATION_SIGNAL_NEXT_ACTION_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'recommendedNextAction',
      type: FieldType.SELECT,
      label: 'Recommended next action',
      icon: 'IconArrowRight',
      defaultValue: `'${NextAction.NO_ACTION}'`,
      options: [
        { value: NextAction.SEND_REPLY, label: 'Send reply now', position: 0, color: 'blue' },
        { value: NextAction.SCHEDULE_FOLLOW_UP, label: 'Schedule follow-up', position: 1, color: 'yellow' },
        { value: NextAction.ESCALATE_TO_HUMAN, label: 'Escalate to human', position: 2, color: 'red' },
        { value: NextAction.MARK_WON, label: 'Mark opportunity won', position: 3, color: 'green' },
        { value: NextAction.MARK_LOST, label: 'Mark opportunity lost', position: 4, color: 'gray' },
        { value: NextAction.NO_ACTION, label: 'No action needed', position: 5, color: 'gray' },
      ],
    },
    {
      universalIdentifier: CONVERSATION_SIGNAL_REPLY_DRAFT_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'recommendedReplyDraft',
      type: FieldType.RICH_TEXT,
      label: 'Recommended reply draft',
      icon: 'IconMailForward',
      description: 'A starting-point draft for a human to review and send -- never sent automatically.',
      isNullable: true,
    },
    {
      universalIdentifier: CONVERSATION_SIGNAL_FOLLOW_UP_AT_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'recommendedFollowUpAt',
      type: FieldType.DATE_TIME,
      label: 'Recommended follow-up at',
      icon: 'IconCalendarTime',
      description: 'Suggested timing for the next touch when the recommended action is a follow-up.',
      isNullable: true,
    },
    {
      universalIdentifier: CONVERSATION_SIGNAL_CONFIDENCE_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'confidence',
      type: FieldType.NUMBER,
      label: 'Confidence',
      icon: 'IconGauge',
      description: '0-1. Clamped and validated by the worker -- never trusted verbatim from the LLM.',
      universalSettings: { dataType: 'float' },
      isNullable: false,
      defaultValue: '0',
    },
    {
      universalIdentifier: CONVERSATION_SIGNAL_SOURCE_MESSAGE_ID_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'sourceMessageId',
      type: FieldType.TEXT,
      label: 'Source message ID',
      icon: 'IconHash',
      description: 'Twenty Message record this analysis was derived from. Used to dedupe re-triggers.',
      isNullable: true,
    },
    {
      universalIdentifier: CONVERSATION_SIGNAL_RAW_EXCERPT_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'rawExcerpt',
      type: FieldType.TEXT,
      label: 'Reply excerpt',
      icon: 'IconQuote',
      description: 'Short excerpt of the analyzed reply, kept for audit -- not the full message body.',
      isNullable: true,
    },
    {
      universalIdentifier: CONVERSATION_SIGNAL_MODEL_USED_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'modelUsed',
      type: FieldType.TEXT,
      label: 'Model used',
      icon: 'IconRobot',
      description: 'Which LLM (provider/model string) produced this analysis, for auditability if the backend changes.',
      isNullable: true,
    },
    {
      universalIdentifier: CONVERSATION_SIGNAL_ERROR_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'errorMessage',
      type: FieldType.TEXT,
      label: 'Error message',
      icon: 'IconAlertTriangle',
      isNullable: true,
    },
  ],
});
