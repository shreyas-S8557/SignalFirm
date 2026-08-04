import { defineObject, FieldType, ObjectOpenRecordIn } from 'twenty-sdk/define';

import {
  RESEARCH_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
  RESEARCH_JOB_STATUS_FIELD_UNIVERSAL_IDENTIFIER,
  RESEARCH_JOB_SOURCE_FIELD_UNIVERSAL_IDENTIFIER,
  RESEARCH_JOB_SOURCE_RUN_ID_FIELD_UNIVERSAL_IDENTIFIER,
  RESEARCH_JOB_SUMMARY_FIELD_UNIVERSAL_IDENTIFIER,
  RESEARCH_JOB_PAIN_POINTS_FIELD_UNIVERSAL_IDENTIFIER,
  RESEARCH_JOB_SALES_ANGLES_FIELD_UNIVERSAL_IDENTIFIER,
  RESEARCH_JOB_BUYING_SIGNALS_FIELD_UNIVERSAL_IDENTIFIER,
  RESEARCH_JOB_CONFIDENCE_FIELD_UNIVERSAL_IDENTIFIER,
  RESEARCH_JOB_MODEL_USED_FIELD_UNIVERSAL_IDENTIFIER,
  RESEARCH_JOB_ERROR_FIELD_UNIVERSAL_IDENTIFIER,
  RESEARCH_JOB_GROUNDING_FIELD_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

/**
 * One record per scrape-to-CRM sync attempt *and* per AI research pass for
 * a single Company. As the original scaffold planned, the research pass
 * (Phase 5) extends this same object's lifecycle with RESEARCHING /
 * RESEARCHED states rather than introducing a parallel object, so a
 * company's full history (import -> enrichment -> research) reads as one
 * timeline instead of three disconnected tables.
 *
 * IMPORTED / SKIPPED / FAILED records are written by sync.py (one per
 * scraped row). RESEARCHING / RESEARCHED / RESEARCH_FAILED records are
 * written by worker/scrapegraph_worker/research/engine.py (one per
 * research run) -- append-only, so re-researching a company preserves the
 * prior run rather than overwriting it.
 *
 * A note on the AI-generated fields below: `summary` and `buyingSignals`
 * are grounded restatements of text actually found on the company's own
 * site (via the EnrichmentJob this research run reads from), while
 * `painPoints` and `salesAngles` are explicitly *inferences* -- plausible
 * hypotheses for a human to evaluate, not established facts about the
 * company. The prompt (see research/prompts.py) forces every item to cite
 * what it was derived from, and `grounding` records the EnrichmentJob and
 * source URLs the run was based on, so any claim here can be traced back
 * rather than taken on faith.
 */
enum ResearchJobStatus {
  IMPORTED = 'IMPORTED',
  SKIPPED = 'SKIPPED',
  FAILED = 'FAILED',
  RESEARCHING = 'RESEARCHING',
  RESEARCHED = 'RESEARCHED',
  RESEARCH_FAILED = 'RESEARCH_FAILED',
}

export default defineObject({
  universalIdentifier: RESEARCH_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
  nameSingular: 'researchJob',
  namePlural: 'researchJobs',
  labelSingular: 'Research Job',
  labelPlural: 'Research Jobs',
  description:
    'Tracks one Scrapegraph sync attempt, or one AI research pass, for a Company.',
  icon: 'IconSearch',
  openRecordIn: ObjectOpenRecordIn.SIDE_PANEL,
  fields: [
    {
      universalIdentifier: RESEARCH_JOB_STATUS_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'status',
      type: FieldType.SELECT,
      label: 'Status',
      icon: 'IconProgressCheck',
      defaultValue: `'${ResearchJobStatus.IMPORTED}'`,
      options: [
        { value: ResearchJobStatus.IMPORTED, label: 'Imported', position: 0, color: 'green' },
        { value: ResearchJobStatus.SKIPPED, label: 'Skipped', position: 1, color: 'gray' },
        { value: ResearchJobStatus.FAILED, label: 'Failed', position: 2, color: 'red' },
        { value: ResearchJobStatus.RESEARCHING, label: 'Researching', position: 3, color: 'blue' },
        { value: ResearchJobStatus.RESEARCHED, label: 'Researched', position: 4, color: 'green' },
        { value: ResearchJobStatus.RESEARCH_FAILED, label: 'Research failed', position: 5, color: 'red' },
      ],
    },
    {
      universalIdentifier: RESEARCH_JOB_SOURCE_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'source',
      type: FieldType.TEXT,
      label: 'Source',
      icon: 'IconDatabaseImport',
      description:
        'Which pipeline produced this row -- a Scrapegraph phase for import records (e.g. linkedin_harvest), or "research-agent" for AI research passes.',
    },
    {
      universalIdentifier: RESEARCH_JOB_SOURCE_RUN_ID_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'sourceRunId',
      type: FieldType.TEXT,
      label: 'Source run ID',
      icon: 'IconHash',
      description: 'The worker-service job ID this record was written by. Used for progress-webhook correlation.',
    },
    {
      universalIdentifier: RESEARCH_JOB_SUMMARY_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'researchSummary',
      type: FieldType.RICH_TEXT,
      label: 'Research summary',
      icon: 'IconFileText',
      description:
        'What this company does and who it sells to, synthesized from enrichment data. A grounded restatement of crawled site text -- not new facts.',
      isNullable: true,
    },
    {
      universalIdentifier: RESEARCH_JOB_PAIN_POINTS_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'painPoints',
      type: FieldType.RICH_TEXT,
      label: 'Pain points (hypotheses)',
      icon: 'IconAlertCircle',
      description:
        'INFERRED, not established: plausible operational/business problems this company may have, each stated with what it was inferred from. Treat as a starting hypothesis for a human to validate on a call, never as a fact to assert to the prospect.',
      isNullable: true,
    },
    {
      universalIdentifier: RESEARCH_JOB_SALES_ANGLES_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'salesAngles',
      type: FieldType.RICH_TEXT,
      label: 'Sales angles (hypotheses)',
      icon: 'IconTargetArrow',
      description:
        'INFERRED, not established: suggested angles for a first conversation, each tied to a pain point above. A human picks and adapts these -- nothing here is sent automatically.',
      isNullable: true,
    },
    {
      universalIdentifier: RESEARCH_JOB_BUYING_SIGNALS_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'researchBuyingSignals',
      type: FieldType.RICH_TEXT,
      label: 'Buying signals (interpreted)',
      icon: 'IconTrendingUp',
      description:
        "The LLM's reading of the keyword-matched buying signals Phase 4 enrichment already found -- an interpretation layered on quoted excerpts, not a new search for signals.",
      isNullable: true,
    },
    {
      universalIdentifier: RESEARCH_JOB_CONFIDENCE_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'researchConfidence',
      type: FieldType.NUMBER,
      label: 'Research confidence',
      icon: 'IconGauge',
      description:
        '0-1, computed deterministically from how much grounding material the run actually had -- never the LLM-emitted number taken at face value.',
      universalSettings: { dataType: 'float' },
      isNullable: true,
    },
    {
      universalIdentifier: RESEARCH_JOB_GROUNDING_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'grounding',
      type: FieldType.TEXT,
      label: 'Grounding',
      icon: 'IconLink',
      description:
        'Which EnrichmentJob and source URLs this research run was based on, so every claim above can be traced back to its input.',
      isNullable: true,
    },
    {
      universalIdentifier: RESEARCH_JOB_MODEL_USED_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'modelUsed',
      type: FieldType.TEXT,
      label: 'Model used',
      icon: 'IconRobot',
      isNullable: true,
    },
    {
      universalIdentifier: RESEARCH_JOB_ERROR_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'errorMessage',
      type: FieldType.TEXT,
      label: 'Error message',
      icon: 'IconAlertTriangle',
      isNullable: true,
    },
  ],
});
