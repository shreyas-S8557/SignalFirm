/**
 * Stable UUIDs for every object, field, and logic function this app owns.
 * These must never change once deployed -- Twenty uses them (not names) to
 * track identity across syncs, so renaming a field in the Twenty UI or in
 * this file later is safe, but changing the UUID here is not.
 */

export const APPLICATION_UNIVERSAL_IDENTIFIER =
  '68ce72ac-6343-49ca-8192-cae7abd1fe07';

// -- ResearchJob --------------------------------------------------------
export const RESEARCH_JOB_OBJECT_UNIVERSAL_IDENTIFIER =
  'c4c3638e-23e1-42c7-a312-5f69d372e60c';
export const RESEARCH_JOB_STATUS_FIELD_UNIVERSAL_IDENTIFIER =
  '4f769605-ac94-42b0-be03-7405c647d238';
export const RESEARCH_JOB_SOURCE_FIELD_UNIVERSAL_IDENTIFIER =
  '6fb4796f-0c05-48eb-8f06-4b0fe2297cff';
export const RESEARCH_JOB_SOURCE_RUN_ID_FIELD_UNIVERSAL_IDENTIFIER =
  '818db2fb-0895-4dcf-b6ce-a29beceaa385';
export const RESEARCH_JOB_COMPANY_FIELD_UNIVERSAL_IDENTIFIER =
  '68f17db9-17fd-4863-b12c-95898fabc278';
export const COMPANY_RESEARCH_JOBS_FIELD_UNIVERSAL_IDENTIFIER =
  'aebd95f4-033a-4f19-bad6-350cc53b04b0';

// -- EnrichmentJob --------------------------------------------------------
export const ENRICHMENT_JOB_OBJECT_UNIVERSAL_IDENTIFIER =
  '3e2dc359-415d-4b6b-9744-bd198278474d';
export const ENRICHMENT_JOB_STATUS_FIELD_UNIVERSAL_IDENTIFIER =
  '768ce978-50ce-4c57-a561-38c876291f05';
export const ENRICHMENT_JOB_PROVIDER_FIELD_UNIVERSAL_IDENTIFIER =
  '66987c26-da5a-4ce6-b426-03d4432c7642';
export const ENRICHMENT_JOB_CONFIDENCE_FIELD_UNIVERSAL_IDENTIFIER =
  'd46c02be-c6f9-4322-95f7-660af944b008';
export const ENRICHMENT_JOB_ERROR_FIELD_UNIVERSAL_IDENTIFIER =
  'c823ec50-b46e-43fd-96f7-400efe5deb56';
export const ENRICHMENT_JOB_COMPANY_FIELD_UNIVERSAL_IDENTIFIER =
  'eaa51a2e-b7bf-4d68-a83d-8b6c3a229d1b';
export const COMPANY_ENRICHMENT_JOBS_FIELD_UNIVERSAL_IDENTIFIER =
  '3271f094-5682-45ad-b906-ea1f6ca71f97';

// -- ICPScore --------------------------------------------------------
export const ICP_SCORE_OBJECT_UNIVERSAL_IDENTIFIER =
  '268dff8e-d639-4d9a-9cb6-92aa8f436679';
export const ICP_SCORE_VALUE_FIELD_UNIVERSAL_IDENTIFIER =
  '999a4f0c-6475-4444-973b-49e2e2a1120e';
export const ICP_SCORE_PRIORITY_FIELD_UNIVERSAL_IDENTIFIER =
  '88930394-b15e-4f05-bef8-9e45acd4ac20';
export const ICP_SCORE_REASONING_FIELD_UNIVERSAL_IDENTIFIER =
  '95d7b3f3-53aa-4c43-9e23-f07986dc6740';
export const ICP_SCORE_CONFIDENCE_FIELD_UNIVERSAL_IDENTIFIER =
  '9b4a1928-abf9-4cb2-b113-ab8707bd6048';
export const ICP_SCORE_RUBRIC_VERSION_FIELD_UNIVERSAL_IDENTIFIER =
  '80f05867-c2e7-4bed-adf0-478466b0410f';
export const ICP_SCORE_COMPANY_FIELD_UNIVERSAL_IDENTIFIER =
  'ebcf41a4-14a7-436c-84e7-b86a7f03da5f';
export const COMPANY_ICP_SCORES_FIELD_UNIVERSAL_IDENTIFIER =
  'ecb12e0c-7ffd-477c-abe7-d5ab9c5420e4';

// -- Convenience fields added onto the standard Company object ----------
// Denormalized "latest value" fields so a plain Company list view can show
// ICP score/priority as a column/badge without joining to ICPScore. The
// full history still lives in ICPScore records.
export const COMPANY_LATEST_ICP_SCORE_FIELD_UNIVERSAL_IDENTIFIER =
  '9e19b506-7359-423e-8aa0-c2f40b73300d';
export const COMPANY_LATEST_ICP_PRIORITY_FIELD_UNIVERSAL_IDENTIFIER =
  'e83297e0-4f94-4b2a-ab9f-2bfb62ae1c5e';
export const COMPANY_LAST_ENRICHED_AT_FIELD_UNIVERSAL_IDENTIFIER =
  '8ea4ee83-1dad-4b4f-9553-25e66a6e38ab';

// -- Logic functions --------------------------------------------------------
export const JOB_PROGRESS_WEBHOOK_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER =
  '8f05f2ef-2009-449d-bd94-6c2955ae15cb';
