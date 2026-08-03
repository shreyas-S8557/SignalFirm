import { defineObject, FieldType, ObjectOpenRecordIn } from 'twenty-sdk/define';

import {
  ENRICHMENT_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_STATUS_FIELD_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_PROVIDER_FIELD_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_CONFIDENCE_FIELD_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_ERROR_FIELD_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

/**
 * Not written to by this milestone's code -- the worker service only writes
 * ResearchJob today. This object is scaffolded now (rather than in a later
 * milestone) so the data model for Phase 4 (CPA Enrichment Pipeline) is
 * settled up front and the UI/relations around it can be built incrementally
 * without a schema migration later. Every result this object will eventually
 * hold must carry a confidence score -- enforced here at the schema level
 * (NUMBER field, not optional) so "no confidence recorded" is never a silent
 * possibility once enrichment logic starts writing to it.
 */
enum EnrichmentJobStatus {
  PENDING = 'PENDING',
  SUCCEEDED = 'SUCCEEDED',
  FAILED = 'FAILED',
  PARTIAL = 'PARTIAL',
}

export default defineObject({
  universalIdentifier: ENRICHMENT_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
  nameSingular: 'enrichmentJob',
  namePlural: 'enrichmentJobs',
  labelSingular: 'Enrichment Job',
  labelPlural: 'Enrichment Jobs',
  description: 'One attempt to enrich a Company with external data (website, headcount, tech stack, etc).',
  icon: 'IconWand',
  openRecordIn: ObjectOpenRecordIn.SIDE_PANEL,
  fields: [
    {
      universalIdentifier: ENRICHMENT_JOB_STATUS_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'status',
      type: FieldType.SELECT,
      label: 'Status',
      icon: 'IconProgressCheck',
      defaultValue: `'${EnrichmentJobStatus.PENDING}'`,
      options: [
        { value: EnrichmentJobStatus.PENDING, label: 'Pending', position: 0, color: 'gray' },
        { value: EnrichmentJobStatus.SUCCEEDED, label: 'Succeeded', position: 1, color: 'green' },
        { value: EnrichmentJobStatus.FAILED, label: 'Failed', position: 2, color: 'red' },
        { value: EnrichmentJobStatus.PARTIAL, label: 'Partial', position: 3, color: 'orange' },
      ],
    },
    {
      universalIdentifier: ENRICHMENT_JOB_PROVIDER_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'provider',
      type: FieldType.TEXT,
      label: 'Provider',
      icon: 'IconPlug',
      description: 'Which enrichment source produced this result (e.g. people-data-labs, company-site-crawl).',
    },
    {
      universalIdentifier: ENRICHMENT_JOB_CONFIDENCE_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'confidence',
      type: FieldType.NUMBER,
      label: 'Confidence',
      icon: 'IconGauge',
      description: '0-1. Never defaulted to a high value -- must be set explicitly by whatever writes this record.',
      universalSettings: { dataType: 'float' },
      isNullable: false,
      defaultValue: '0',
    },
    {
      universalIdentifier: ENRICHMENT_JOB_ERROR_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'errorMessage',
      type: FieldType.TEXT,
      label: 'Error message',
      icon: 'IconAlertTriangle',
      isNullable: true,
    },
  ],
});
