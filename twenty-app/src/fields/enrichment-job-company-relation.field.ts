import {
  defineField,
  FieldType,
  OnDeleteAction,
  RelationType,
  STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS,
} from 'twenty-sdk/define';

import {
  ENRICHMENT_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_COMPANY_FIELD_UNIVERSAL_IDENTIFIER,
  COMPANY_ENRICHMENT_JOBS_FIELD_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

export default defineField({
  universalIdentifier: ENRICHMENT_JOB_COMPANY_FIELD_UNIVERSAL_IDENTIFIER,
  objectUniversalIdentifier: ENRICHMENT_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
  type: FieldType.RELATION,
  name: 'company',
  label: 'Company',
  icon: 'IconBuilding',
  relationTargetObjectMetadataUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  relationTargetFieldMetadataUniversalIdentifier: COMPANY_ENRICHMENT_JOBS_FIELD_UNIVERSAL_IDENTIFIER,
  universalSettings: {
    relationType: RelationType.MANY_TO_ONE,
    onDelete: OnDeleteAction.CASCADE,
    joinColumnName: 'companyId',
  },
});
