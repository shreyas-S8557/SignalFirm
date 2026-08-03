import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { PERSON_LATEST_INTEREST_LEVEL_FIELD_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';

/**
 * Denormalized "latest value" so a plain People table view can sort/filter
 * by interest level without joining to ConversationSignal records. Written
 * by conversation-signal-webhook.ts every time a new ConversationSignal is
 * created for this person (overwritten each time -- full history lives on
 * the ConversationSignal records themselves).
 */
export default defineField({
  universalIdentifier: PERSON_LATEST_INTEREST_LEVEL_FIELD_UNIVERSAL_IDENTIFIER,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.person.universalIdentifier,
  type: FieldType.SELECT,
  name: 'latestInterestLevel',
  label: 'Latest interest level',
  icon: 'IconFlame',
  isNullable: true,
  options: [
    { value: 'HIGH', label: 'High', position: 0, color: 'green' },
    { value: 'MEDIUM', label: 'Medium', position: 1, color: 'yellow' },
    { value: 'LOW', label: 'Low', position: 2, color: 'orange' },
    { value: 'NONE', label: 'None detected', position: 3, color: 'gray' },
  ],
});
