import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { COMPANY_LAST_ENRICHED_AT_FIELD_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';

// Written by this milestone's sync.py indirectly is out of scope (no
// enrichment happens yet) -- reserved for the enrichment logic function.
export default defineField({
  universalIdentifier: COMPANY_LAST_ENRICHED_AT_FIELD_UNIVERSAL_IDENTIFIER,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  type: FieldType.DATE_TIME,
  name: 'lastEnrichedAt',
  label: 'Last enriched at',
  icon: 'IconClock',
  isNullable: true,
});
