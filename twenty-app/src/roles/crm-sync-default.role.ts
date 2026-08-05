import { defineApplicationRole } from 'twenty-sdk/define';

import {
  APPLICATION_ROLE_UNIVERSAL_IDENTIFIER,
  RESEARCH_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
  ICP_SCORE_OBJECT_UNIVERSAL_IDENTIFIER,
  CONVERSATION_SIGNAL_OBJECT_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

/**
 * Twenty SDK 2.27 requires every application to declare a default role.
 * `defaultRoleUniversalIdentifier` on defineApplication() still exists but
 * is deprecated in favor of marking exactly one role file with
 * defineApplicationRole() (only one is allowed per application) -- see
 * https://docs.twenty.com/developers/extend/apps for the current pattern.
 *
 * This app doesn't gate any workspace-wide settings or tools behind a
 * custom role -- it just needs whoever installs it to be able to read and
 * write the four objects it owns (ResearchJob, EnrichmentJob, ICPScore,
 * ConversationSignal). Everything else (Company/Person/etc, which this app
 * only adds fields/relations onto) is governed by the workspace's own
 * existing roles, not this one.
 */
export default defineApplicationRole({
  universalIdentifier: APPLICATION_ROLE_UNIVERSAL_IDENTIFIER,
  label: 'CRM Sync (Scrapegraph)',
  description:
    'Default role installed with the CRM Sync app. Grants full read/write ' +
    'access to the Research Job, Enrichment Job, ICP Score, and ' +
    'Conversation Signal objects this app owns.',
  icon: 'IconPlugConnected',
  canBeAssignedToUsers: true,
  canBeAssignedToAgents: true,
  canBeAssignedToApiKeys: true,
  objectPermissions: [
    {
      objectUniversalIdentifier: RESEARCH_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
      canReadObjectRecords: true,
      canUpdateObjectRecords: true,
      canSoftDeleteObjectRecords: true,
      canDestroyObjectRecords: false,
    },
    {
      objectUniversalIdentifier: ENRICHMENT_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
      canReadObjectRecords: true,
      canUpdateObjectRecords: true,
      canSoftDeleteObjectRecords: true,
      canDestroyObjectRecords: false,
    },
    {
      objectUniversalIdentifier: ICP_SCORE_OBJECT_UNIVERSAL_IDENTIFIER,
      canReadObjectRecords: true,
      canUpdateObjectRecords: true,
      canSoftDeleteObjectRecords: true,
      canDestroyObjectRecords: false,
    },
    {
      objectUniversalIdentifier: CONVERSATION_SIGNAL_OBJECT_UNIVERSAL_IDENTIFIER,
      canReadObjectRecords: true,
      canUpdateObjectRecords: true,
      canSoftDeleteObjectRecords: true,
      canDestroyObjectRecords: false,
    },
  ],
});
