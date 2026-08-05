import { defineObject, FieldType, NumberDataType, ObjectOpenRecordIn } from 'twenty-sdk/define';

import {
  ENRICHMENT_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_STATUS_FIELD_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_PROVIDER_FIELD_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_CONFIDENCE_FIELD_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_ERROR_FIELD_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_SUMMARY_FIELD_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_TECH_STACK_FIELD_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_HIRING_SIGNALS_FIELD_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_BUYING_SIGNALS_FIELD_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_GROWTH_INDICATORS_FIELD_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_AI_MATURITY_FIELD_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_SOURCES_CHECKED_FIELD_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

/**
 * Phase 4 (Company Enrichment) now writes to this object -- see
 * worker/scrapegraph_worker/enrichment/engine.py. `provider` is always
 * "site-crawl" today: every signal here is derived from the company's own
 * public website (crawled directly) plus People records already synced
 * into this workspace (a LinkedIn-derived headcount/seniority proxy, not a
 * live LinkedIn scrape -- LinkedIn's terms of service prohibit automated
 * scraping of its site, so this pipeline deliberately never fetches
 * linkedin.com directly; see worker/scrapegraph_worker/enrichment/signals.py
 * for the reasoning). `provider` stays a free-text field rather than a closed enum
 * so a future paid data provider (Clearbit, Apollo, PDL, etc.) can be
 * plugged in later without a schema change.
 *
 * Every result this object holds carries a confidence score -- enforced
 * here at the schema level (NUMBER field, not optional) so "no confidence
 * recorded" is never a silent possibility.
 */
enum EnrichmentJobStatus {
  PENDING = 'PENDING',
  SUCCEEDED = 'SUCCEEDED',
  FAILED = 'FAILED',
  PARTIAL = 'PARTIAL',
}

enum AIMaturityLevel {
  UNKNOWN = 'UNKNOWN',
  NONE_OBSERVED = 'NONE_OBSERVED',
  EXPLORING = 'EXPLORING',
  ADOPTING = 'ADOPTING',
  ADVANCED = 'ADVANCED',
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
      description: 'Which enrichment source produced this result -- always "site-crawl" today (see enrichment/engine.py); a future paid provider would add a new value here, e.g. "people-data-labs".',
    },
    {
      universalIdentifier: ENRICHMENT_JOB_CONFIDENCE_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'confidence',
      type: FieldType.NUMBER,
      label: 'Confidence',
      icon: 'IconGauge',
      description: '0-1. Never defaulted to a high value -- must be set explicitly by whatever writes this record.',
      universalSettings: { dataType: NumberDataType.FLOAT },
      isNullable: false,
      defaultValue: 0,
    },
    {
      universalIdentifier: ENRICHMENT_JOB_ERROR_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'errorMessage',
      type: FieldType.TEXT,
      label: 'Error message',
      icon: 'IconAlertTriangle',
      isNullable: true,
    },
    {
      universalIdentifier: ENRICHMENT_JOB_SUMMARY_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'summary',
      type: FieldType.RICH_TEXT,
      label: 'Company summary',
      icon: 'IconFileText',
      description: 'LLM-synthesized 2-4 sentence summary of what the company does, grounded in crawled site text. Falls back to a heuristic (title/meta-description) summary when no LLM is configured.',
      isNullable: true,
    },
    {
      universalIdentifier: ENRICHMENT_JOB_TECH_STACK_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'techStack',
      type: FieldType.TEXT,
      label: 'Tech stack',
      icon: 'IconStack2',
      description: 'Comma-separated technologies detected via signature matching against crawled HTML (script sources, meta generator tags, marker cookies) -- e.g. "HubSpot, WordPress, Google Analytics, Stripe".',
      isNullable: true,
    },
    {
      universalIdentifier: ENRICHMENT_JOB_HIRING_SIGNALS_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'hiringSignals',
      type: FieldType.RICH_TEXT,
      label: 'Hiring signals',
      icon: 'IconUserPlus',
      description: 'Open roles and hiring-related keywords found on the company\'s own careers/jobs page, grouped by function where detectable.',
      isNullable: true,
    },
    {
      universalIdentifier: ENRICHMENT_JOB_BUYING_SIGNALS_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'buyingSignals',
      type: FieldType.RICH_TEXT,
      label: 'Buying signals',
      icon: 'IconTrendingUp',
      description: 'Keyword-matched phrases from crawled pages suggesting active change (funding, new leadership, expansion, RFPs, "looking for a partner", etc). Always a quoted excerpt plus source URL -- never a fabricated claim.',
      isNullable: true,
    },
    {
      universalIdentifier: ENRICHMENT_JOB_GROWTH_INDICATORS_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'growthIndicators',
      type: FieldType.RICH_TEXT,
      label: 'Growth indicators',
      icon: 'IconChartLine',
      description: 'Headcount proxy (count of this company\'s People records already synced from LinkedIn-sourced leads) plus open-role volume, as a lightweight substitute for a real headcount-over-time API.',
      isNullable: true,
    },
    {
      universalIdentifier: ENRICHMENT_JOB_AI_MATURITY_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'aiMaturity',
      type: FieldType.SELECT,
      label: 'AI maturity',
      icon: 'IconRobot',
      description: 'Heuristic/LLM read on how AI-forward the company appears from its own public site (careers page AI roles, product pages mentioning AI/ML, etc). Never a confident claim -- treat as a conversation-starter signal, not a fact.',
      defaultValue: `'${AIMaturityLevel.UNKNOWN}'`,
      options: [
        { value: AIMaturityLevel.UNKNOWN, label: 'Unknown', position: 0, color: 'gray' },
        { value: AIMaturityLevel.NONE_OBSERVED, label: 'None observed', position: 1, color: 'gray' },
        { value: AIMaturityLevel.EXPLORING, label: 'Exploring', position: 2, color: 'blue' },
        { value: AIMaturityLevel.ADOPTING, label: 'Adopting', position: 3, color: 'yellow' },
        { value: AIMaturityLevel.ADVANCED, label: 'Advanced', position: 4, color: 'green' },
      ],
    },
    {
      universalIdentifier: ENRICHMENT_JOB_SOURCES_CHECKED_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'sourcesChecked',
      type: FieldType.TEXT,
      label: 'Sources checked',
      icon: 'IconLink',
      description: 'Comma-separated URLs this run actually fetched, for auditability (e.g. so a PARTIAL result can be understood -- which pages were and weren\'t reachable).',
      isNullable: true,
    },
  ],
});
