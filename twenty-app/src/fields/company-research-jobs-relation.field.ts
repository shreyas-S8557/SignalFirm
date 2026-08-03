import {
  defineField,
  FieldType,
  RelationType,
  STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS,
} from 'twenty-sdk/define';

import {
  RESEARCH_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
  RESEARCH_JOB_COMPANY_FIELD_UNIVERSAL_IDENTIFIER,
  COMPANY_RESEARCH_JOBS_FIELD_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

// The "one" side, added onto the standard Company object we don't own.
export default defineField({
  universalIdentifier: COMPANY_RESEARCH_JOBS_FIELD_UNIVERSAL_IDENTIFIER,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  type: FieldType.RELATION,
  name: 'researchJobs',
  label: 'Research Jobs',
  icon: 'IconSearch',
  relationTargetObjectMetadataUniversalIdentifier: RESEARCH_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
  relationTargetFieldMetadataUniversalIdentifier: RESEARCH_JOB_COMPANY_FIELD_UNIVERSAL_IDENTIFIER,
  universalSettings: {
    relationType: RelationType.ONE_TO_MANY,
  },
});
