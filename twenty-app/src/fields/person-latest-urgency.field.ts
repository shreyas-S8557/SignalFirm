import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { PERSON_LATEST_URGENCY_FIELD_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';

// Denormalized alongside latestInterestLevel -- see that field's comment.
export default defineField({
  universalIdentifier: PERSON_LATEST_URGENCY_FIELD_UNIVERSAL_IDENTIFIER,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.person.universalIdentifier,
  type: FieldType.SELECT,
  name: 'latestUrgency',
  label: 'Latest urgency',
  icon: 'IconAlarm',
  isNullable: true,
  options: [
    { value: 'HIGH', label: 'High', position: 0, color: 'red' },
    { value: 'MEDIUM', label: 'Medium', position: 1, color: 'yellow' },
    { value: 'LOW', label: 'Low', position: 2, color: 'gray' },
  ],
});
