import {
  defineField,
  FieldType,
  OnDeleteAction,
  RelationType,
  STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS,
} from 'twenty-sdk/define';

import {
  RESEARCH_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
  RESEARCH_JOB_COMPANY_FIELD_UNIVERSAL_IDENTIFIER,
  COMPANY_RESEARCH_JOBS_FIELD_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

// The "many" side: each ResearchJob belongs to (at most) one Company.
// A ResearchJob with no company (e.g. a row that couldn't be matched to any
// company at all) is valid -- hence SET_NULL rather than CASCADE, and the
// field is nullable.
export default defineField({
  universalIdentifier: RESEARCH_JOB_COMPANY_FIELD_UNIVERSAL_IDENTIFIER,
  objectUniversalIdentifier: RESEARCH_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
  type: FieldType.RELATION,
  name: 'company',
  label: 'Company',
  icon: 'IconBuilding',
  relationTargetObjectMetadataUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  relationTargetFieldMetadataUniversalIdentifier: COMPANY_RESEARCH_JOBS_FIELD_UNIVERSAL_IDENTIFIER,
  universalSettings: {
    relationType: RelationType.MANY_TO_ONE,
    onDelete: OnDeleteAction.SET_NULL,
    joinColumnName: 'companyId',
  },
});
