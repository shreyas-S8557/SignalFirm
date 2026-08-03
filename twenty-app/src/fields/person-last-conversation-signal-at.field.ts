import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { PERSON_LAST_CONVERSATION_SIGNAL_AT_FIELD_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';

// Denormalized alongside latestInterestLevel -- see that field's comment.
export default defineField({
  universalIdentifier: PERSON_LAST_CONVERSATION_SIGNAL_AT_FIELD_UNIVERSAL_IDENTIFIER,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.person.universalIdentifier,
  type: FieldType.DATE_TIME,
  name: 'lastConversationSignalAt',
  label: 'Last conversation signal at',
  icon: 'IconClock',
  isNullable: true,
});
