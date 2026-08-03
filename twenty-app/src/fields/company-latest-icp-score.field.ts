import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { COMPANY_LATEST_ICP_SCORE_FIELD_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';

/**
 * Denormalized "latest value," so a plain Company table view can sort/filter
 * by ICP score without joining to ICPScore records. Not written to by this
 * milestone -- stays null until the ICP Scoring logic function (a later
 * milestone) starts writing the newest ICPScore's value here. Scaffolded now
 * so the UI (Phase 10) can be built against a stable schema.
 */
export default defineField({
  universalIdentifier: COMPANY_LATEST_ICP_SCORE_FIELD_UNIVERSAL_IDENTIFIER,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  type: FieldType.NUMBER,
  name: 'latestIcpScore',
  label: 'ICP Score',
  icon: 'IconGauge',
  universalSettings: { dataType: 'float' },
  isNullable: true,
});
