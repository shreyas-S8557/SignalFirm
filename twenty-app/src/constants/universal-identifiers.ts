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
// -- ResearchJob AI-research fields (Phase 5: Research Automation) -------
// The research pass extends this same object's lifecycle (adding
// RESEARCHING / RESEARCHED statuses) rather than introducing a parallel
// object -- exactly as research-job.object.ts's original comment planned,
// so a company's import -> enrichment -> research history reads as one
// timeline. Written by worker/scrapegraph_worker/research/engine.py.
export const RESEARCH_JOB_SUMMARY_FIELD_UNIVERSAL_IDENTIFIER =
  'a9e795f0-95d3-4ce4-8b86-14b47581626b';
export const RESEARCH_JOB_PAIN_POINTS_FIELD_UNIVERSAL_IDENTIFIER =
  '7a3f41d9-71c5-4a8f-b729-bd73dcb7d396';
export const RESEARCH_JOB_SALES_ANGLES_FIELD_UNIVERSAL_IDENTIFIER =
  '6e4f8e19-85e1-46a0-a8a9-f0bf3491d30f';
export const RESEARCH_JOB_BUYING_SIGNALS_FIELD_UNIVERSAL_IDENTIFIER =
  '8908e329-ea9f-4579-8b7c-c31be0754b5a';
export const RESEARCH_JOB_CONFIDENCE_FIELD_UNIVERSAL_IDENTIFIER =
  '3a734c6c-08ea-4331-93a0-60d7da1dd14f';
export const RESEARCH_JOB_MODEL_USED_FIELD_UNIVERSAL_IDENTIFIER =
  'c284203d-ec5f-4bbe-9f12-07d104dab83b';
export const RESEARCH_JOB_ERROR_FIELD_UNIVERSAL_IDENTIFIER =
  '503653fe-029e-481d-963e-fd14589fb67b';
export const RESEARCH_JOB_GROUNDING_FIELD_UNIVERSAL_IDENTIFIER =
  '6ea70254-bef4-43b6-9bb2-c7db842c10f9';

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
// -- EnrichmentJob content fields (Phase 4: Company Enrichment) ----------
// Added once the enrichment engine (worker/scrapegraph_worker/enrichment/)
// actually started writing results, rather than at scaffold time -- see
// that module's README for what populates each of these.
export const ENRICHMENT_JOB_SUMMARY_FIELD_UNIVERSAL_IDENTIFIER =
  '2956333e-9510-49e7-8bb8-fd72711937ef';
export const ENRICHMENT_JOB_TECH_STACK_FIELD_UNIVERSAL_IDENTIFIER =
  '6cc2c9d5-a463-43de-9a6e-7baac66b7695';
export const ENRICHMENT_JOB_HIRING_SIGNALS_FIELD_UNIVERSAL_IDENTIFIER =
  '3df220c7-7fb6-4428-9f83-ae5ebe05727f';
export const ENRICHMENT_JOB_BUYING_SIGNALS_FIELD_UNIVERSAL_IDENTIFIER =
  '5af0391a-aa78-477a-9055-5eb2eafecef3';
export const ENRICHMENT_JOB_GROWTH_INDICATORS_FIELD_UNIVERSAL_IDENTIFIER =
  '70ad1c1f-999b-447f-a537-ad8fbaa77c12';
export const ENRICHMENT_JOB_AI_MATURITY_FIELD_UNIVERSAL_IDENTIFIER =
  '4773355e-d648-4dc2-b15c-40494b71d371';
export const ENRICHMENT_JOB_SOURCES_CHECKED_FIELD_UNIVERSAL_IDENTIFIER =
  '37b90b09-458d-4267-8aef-536d495e9e57';

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

// -- ConversationSignal (Prompt 5: Conversation Intelligence) ------------
export const CONVERSATION_SIGNAL_OBJECT_UNIVERSAL_IDENTIFIER =
  '500b4651-e92f-4e37-b379-67816c260117';
export const CONVERSATION_SIGNAL_STATUS_FIELD_UNIVERSAL_IDENTIFIER =
  'b1349ec6-28d9-44b9-bdb0-e4b867a411e9';
export const CONVERSATION_SIGNAL_INTEREST_LEVEL_FIELD_UNIVERSAL_IDENTIFIER =
  '99c8d6b1-9a27-4e15-b509-220d5afb780c';
export const CONVERSATION_SIGNAL_URGENCY_FIELD_UNIVERSAL_IDENTIFIER =
  '990a2f0a-7dd8-47fe-8079-fff2d0d72490';
export const CONVERSATION_SIGNAL_SENTIMENT_FIELD_UNIVERSAL_IDENTIFIER =
  '271e26ab-a96d-4f14-8bf1-e9310c81d7f3';
export const CONVERSATION_SIGNAL_OBJECTIONS_FIELD_UNIVERSAL_IDENTIFIER =
  'b9503fce-2346-4209-b543-c1a6601771eb';
export const CONVERSATION_SIGNAL_NEXT_ACTION_FIELD_UNIVERSAL_IDENTIFIER =
  'e50c7aa6-cf69-4abb-b306-2c0968e49d68';
export const CONVERSATION_SIGNAL_REPLY_DRAFT_FIELD_UNIVERSAL_IDENTIFIER =
  'af44f2b5-7eb2-4288-bd0b-7c78dfecd091';
export const CONVERSATION_SIGNAL_FOLLOW_UP_AT_FIELD_UNIVERSAL_IDENTIFIER =
  'a2002120-7dd1-4701-a9ae-39316f0086b1';
export const CONVERSATION_SIGNAL_CONFIDENCE_FIELD_UNIVERSAL_IDENTIFIER =
  '614eac6d-48f0-4a04-abad-bb688742d979';
export const CONVERSATION_SIGNAL_SOURCE_MESSAGE_ID_FIELD_UNIVERSAL_IDENTIFIER =
  '76e96815-da74-48f5-9eab-2e09d4ba8a3b';
export const CONVERSATION_SIGNAL_RAW_EXCERPT_FIELD_UNIVERSAL_IDENTIFIER =
  'd6ca74d1-cb0c-4a63-a1ba-92c201164320';
export const CONVERSATION_SIGNAL_ERROR_FIELD_UNIVERSAL_IDENTIFIER =
  'b8ab4daf-90cf-4b7e-850a-fd9d6370d689';
export const CONVERSATION_SIGNAL_MODEL_USED_FIELD_UNIVERSAL_IDENTIFIER =
  'd3c5fa7e-b1aa-4039-a018-bb75af3c3fad';
export const CONVERSATION_SIGNAL_PERSON_FIELD_UNIVERSAL_IDENTIFIER =
  '61743f0e-a5d9-498c-90c7-5d727f3d1268';
export const PERSON_CONVERSATION_SIGNALS_FIELD_UNIVERSAL_IDENTIFIER =
  'da1ef5be-f8d2-431f-8e53-5a8c3993ebce';

// -- Convenience fields added onto the standard Person object ------------
// Denormalized "latest signal" fields so a Person list view can show
// interest/urgency without joining to ConversationSignal. Full history
// still lives in ConversationSignal records.
export const PERSON_LATEST_INTEREST_LEVEL_FIELD_UNIVERSAL_IDENTIFIER =
  '27e0ece1-954d-4301-8b42-f051ca7c6c66';
export const PERSON_LATEST_URGENCY_FIELD_UNIVERSAL_IDENTIFIER =
  '8a10a06e-6354-4b52-9df2-0d569612c26a';
export const PERSON_LAST_CONVERSATION_SIGNAL_AT_FIELD_UNIVERSAL_IDENTIFIER =
  'a1960f52-dc31-44a5-acb5-4f607a29e20c';

// -- Logic functions --------------------------------------------------------
export const JOB_PROGRESS_WEBHOOK_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER =
  '8f05f2ef-2009-449d-bd94-6c2955ae15cb';
// Fires when Twenty's own email sync creates a new Message record; filters
// down to inbound replies and forwards them to the worker's Conversation
// Intelligence endpoint for LLM analysis.
export const REPLY_INTELLIGENCE_TRIGGER_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER =
  'a6941bf6-9eca-4237-b466-c73e3fabe8a3';
// Receives the analysis result back from the worker and writes a
// ConversationSignal record (+ denormalized Person fields).
export const CONVERSATION_SIGNAL_WEBHOOK_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER =
  'aa585acb-0e55-4b88-aef0-e4e12eb7d830';

// -- Phase 8: Twenty Frontend Integration --------------------------------
// Server-side proxy routes: front components (browser-executed, can't hold
// secrets) call these; these forward to the worker service server-to-server,
// attaching CRM_SYNC_WORKER_API_KEY if configured. See src/lib/worker-proxy.ts.
export const WORKER_READ_PROXY_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER =
  '4bd2c42e-4ccf-45d2-8505-3d26b9d429d9';
export const WORKER_DAILY_DIGEST_PROXY_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER =
  'e9a1aa26-f60e-4722-998a-6f658f49a8f8';
export const WORKER_ACTION_PROXY_LOGIC_FUNCTION_UNIVERSAL_IDENTIFIER =
  '9d6d69f5-d803-4c9b-bf09-6ded31421e0a';

// Front components (React, rendered inside Twenty's own UI via Remote DOM).
export const AI_INSIGHTS_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER =
  '8d698f88-c28e-4be4-a5a4-1ac813b6d5e9';
export const RESEARCH_TAB_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER =
  'e0123549-ee56-4f15-9cda-c4cc04b38f8e';
export const CONVERSATION_PANEL_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER =
  '0be672c8-3bfc-4c71-88a8-01eece18b4d8';
export const RECOMMENDATIONS_WIDGET_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER =
  'c8b9a271-181b-4a19-a00f-5349cd8d9541';

// Page layout tabs added onto Twenty's *standard* Company/Person record
// pages (see page-layouts/*.ts -- COMPANY_RECORD_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER
// and PERSON_RECORD_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER there are placeholders
// that must be filled in per-workspace; see that file's comment).
export const COMPANY_AI_INSIGHTS_PAGE_LAYOUT_TAB_UNIVERSAL_IDENTIFIER =
  '9341955e-50df-43f6-b5da-4340e2a8bad2';
export const COMPANY_AI_INSIGHTS_TAB_WIDGET_UNIVERSAL_IDENTIFIER =
  '64f26e01-f86b-4b2f-ab9c-2b960d3770d2';
export const COMPANY_RESEARCH_PAGE_LAYOUT_TAB_UNIVERSAL_IDENTIFIER =
  '45b0203c-b2bf-4a39-a454-8b9de384b9ad';
export const COMPANY_RESEARCH_TAB_WIDGET_UNIVERSAL_IDENTIFIER =
  '9116217d-70e6-4035-89f1-0715efc8473f';
export const PERSON_CONVERSATION_PAGE_LAYOUT_TAB_UNIVERSAL_IDENTIFIER =
  '7a43088c-5dc7-4ce6-8f47-089753c3c4cb';
export const PERSON_CONVERSATION_TAB_WIDGET_UNIVERSAL_IDENTIFIER =
  '0ec439c5-51a5-4a73-aa08-7c67f6d7e954';

// A standalone (not record-scoped) dashboard page for the Recommendation
// Engine's daily digest, plus its own navigation item -- this app owns this
// entire layout (unlike the tabs above, which extend standard layouts).
export const RECOMMENDATIONS_STANDALONE_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER =
  '49152598-fc9e-4965-8253-5e2e130b82fd';
export const RECOMMENDATIONS_PAGE_TAB_UNIVERSAL_IDENTIFIER =
  '061d53b0-c169-4c6b-85bc-e919daf1fce7';
export const RECOMMENDATIONS_PAGE_TAB_WIDGET_UNIVERSAL_IDENTIFIER =
  '7cbc0a0a-60b6-4da0-89d2-9761daccb897';
export const RECOMMENDATIONS_NAVIGATION_ITEM_UNIVERSAL_IDENTIFIER =
  '7c03aded-97a0-4cbc-88cd-6066edbac59a';
