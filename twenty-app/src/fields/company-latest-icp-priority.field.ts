import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { COMPANY_LATEST_ICP_PRIORITY_FIELD_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';

// Denormalized alongside latestIcpScore -- see that field's comment.
export default defineField({
  universalIdentifier: COMPANY_LATEST_ICP_PRIORITY_FIELD_UNIVERSAL_IDENTIFIER,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  type: FieldType.SELECT,
  name: 'latestIcpPriority',
  label: 'ICP Priority',
  icon: 'IconFlag',
  isNullable: true,
  options: [
    { value: 'HIGH', label: 'High', position: 0, color: 'red' },
    { value: 'MEDIUM', label: 'Medium', position: 1, color: 'yellow' },
    { value: 'LOW', label: 'Low', position: 2, color: 'gray' },
  ],
});
