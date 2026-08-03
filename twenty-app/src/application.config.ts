import { defineApplication } from 'twenty-sdk/define';

import { APPLICATION_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';

export default defineApplication({
  universalIdentifier: APPLICATION_UNIVERSAL_IDENTIFIER,
  displayName: 'CRM Sync (Scrapegraph)',
  description:
    'Data-plumbing layer for the Scrapegraph -> Twenty integration: custom ' +
    'objects for research/enrichment jobs and ICP scores, plus a webhook ' +
    'route the Scrapegraph worker service uses to report job progress. ' +
    'No AI logic lives in this app -- see the "AI Service Layer" apps that ' +
    'build on top of these objects in later milestones.',
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
        'Shared secret the Scrapegraph worker service must send as a ' +
        'Bearer token when POSTing job progress to /s/crm-sync/job-progress. ' +
        'Must match TWENTY_WEBHOOK_SHARED_SECRET in the worker service\'s ' +
        'own .env.',
      isSecret: true,
      isRequired: true,
    },
  },
});
