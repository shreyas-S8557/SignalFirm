import { defineApplication } from 'twenty-sdk/define';

import { APPLICATION_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';

export default defineApplication({
  universalIdentifier: APPLICATION_UNIVERSAL_IDENTIFIER,
  displayName: 'CRM Sync (Scrapegraph)',
  description:
    'Data-plumbing layer for the Scrapegraph -> Twenty integration: custom ' +
    'objects for research/enrichment jobs, ICP scores, and conversation ' +
    'signals, plus webhook routes and a database-event trigger the worker ' +
    'service uses to exchange job progress and reply analysis. No AI logic ' +
    'lives in this app -- all LLM calls happen in the worker service (see ' +
    'worker/scrapegraph_worker/conversation/).',
  author: 'Opika',
  category: 'Sales',
  logoUrl: 'public/logo.svg',
  websiteUrl: 'https://docs.twenty.com/developers/extend/apps/getting-started',
  termsUrl: '',
  emailSupport: '',
  issueReportUrl: '',
  serverVariables: {
    SCRAPE_WORKER_WEBHOOK_SHARED_SECRET: {
      description:
        'Shared secret used on BOTH webhook directions: the worker sends ' +
        'it as a Bearer token when POSTing to /s/crm-sync/job-progress and ' +
        '/s/crm-sync/conversation-signal, and reply-intelligence-trigger.ts ' +
        "sends it as a Bearer token when POSTing to the worker's " +
        '/conversation/analyze endpoint. Must match TWENTY_WEBHOOK_SHARED_SECRET ' +
        "in the worker service's own .env.",
      isSecret: true,
      isRequired: true,
    },
    CONVERSATION_WORKER_BASE_URL: {
      description:
        'Base URL of the worker service (e.g. http://worker:8000 or ' +
        'https://worker.yourcompany.com), used by reply-intelligence-trigger.ts ' +
        'to POST inbound replies for analysis. Leave unset to disable the ' +
        'trigger entirely (it no-ops rather than failing). Also used by ' +
        'Phase 8\'s worker-*-proxy.ts logic functions as the base URL for ' +
        'every worker read/action they forward to.',
      isSecret: false,
      isRequired: false,
    },
    CRM_SYNC_WORKER_API_KEY: {
      description:
        'Optional -- only needed if the worker service has WORKER_API_KEY ' +
        'set (see worker/.env.example). When set, every worker-*-proxy.ts ' +
        'logic function sends this as an X-Api-Key header. Leave both ' +
        'sides unset to keep the worker\'s read endpoints open the way ' +
        'they always have been for the Phase 9 standalone frontend.',
      isSecret: true,
      isRequired: false,
    },
  },
});
