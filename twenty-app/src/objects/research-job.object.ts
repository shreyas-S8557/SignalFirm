import { defineObject, FieldType, ObjectOpenRecordIn } from 'twenty-sdk/define';

import {
  RESEARCH_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
  RESEARCH_JOB_STATUS_FIELD_UNIVERSAL_IDENTIFIER,
  RESEARCH_JOB_SOURCE_FIELD_UNIVERSAL_IDENTIFIER,
  RESEARCH_JOB_SOURCE_RUN_ID_FIELD_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

/**
 * One record per scrape-to-CRM sync attempt for a single scraped row. This
 * milestone only ever writes IMPORTED / SKIPPED / FAILED -- the AI research
 * pass (a later milestone) will extend this same object's lifecycle with
 * RESEARCHING / RESEARCHED states rather than introducing a parallel object,
 * so a company's full history (import -> enrichment -> research) reads as
 * one timeline instead of three disconnected tables.
 */
enum ResearchJobStatus {
  IMPORTED = 'IMPORTED',
  SKIPPED = 'SKIPPED',
  FAILED = 'FAILED',
}

export default defineObject({
  universalIdentifier: RESEARCH_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
  nameSingular: 'researchJob',
  namePlural: 'researchJobs',
  labelSingular: 'Research Job',
  labelPlural: 'Research Jobs',
  description:
    'Tracks one Scrapegraph sync attempt (and, later, the AI research pass) for a Company.',
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
      ],
    },
    {
      universalIdentifier: RESEARCH_JOB_SOURCE_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'source',
      type: FieldType.TEXT,
      label: 'Source',
      icon: 'IconDatabaseImport',
      description: 'Which Scrapegraph phase produced this row (e.g. linkedin_harvest, ddgs_search).',
    },
    {
      universalIdentifier: RESEARCH_JOB_SOURCE_RUN_ID_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'sourceRunId',
      type: FieldType.TEXT,
      label: 'Source run ID',
      icon: 'IconHash',
      description: 'The worker-service job ID this record was written by. Used for progress-webhook correlation.',
    },
  ],
});
