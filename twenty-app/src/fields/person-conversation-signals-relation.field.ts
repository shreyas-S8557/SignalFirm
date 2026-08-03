import {
  defineField,
  FieldType,
  RelationType,
  STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS,
} from 'twenty-sdk/define';

import {
  CONVERSATION_SIGNAL_OBJECT_UNIVERSAL_IDENTIFIER,
  CONVERSATION_SIGNAL_PERSON_FIELD_UNIVERSAL_IDENTIFIER,
  PERSON_CONVERSATION_SIGNALS_FIELD_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

export default defineField({
  universalIdentifier: PERSON_CONVERSATION_SIGNALS_FIELD_UNIVERSAL_IDENTIFIER,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.person.universalIdentifier,
  type: FieldType.RELATION,
  name: 'conversationSignals',
  label: 'Conversation Signals',
  icon: 'IconMessageCircle2',
  relationTargetObjectMetadataUniversalIdentifier: CONVERSATION_SIGNAL_OBJECT_UNIVERSAL_IDENTIFIER,
  relationTargetFieldMetadataUniversalIdentifier: CONVERSATION_SIGNAL_PERSON_FIELD_UNIVERSAL_IDENTIFIER,
  universalSettings: {
    relationType: RelationType.ONE_TO_MANY,
  },
});
