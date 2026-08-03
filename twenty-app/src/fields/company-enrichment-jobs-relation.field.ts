import {
  defineField,
  FieldType,
  RelationType,
  STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS,
} from 'twenty-sdk/define';

import {
  ENRICHMENT_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
  ENRICHMENT_JOB_COMPANY_FIELD_UNIVERSAL_IDENTIFIER,
  COMPANY_ENRICHMENT_JOBS_FIELD_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

export default defineField({
  universalIdentifier: COMPANY_ENRICHMENT_JOBS_FIELD_UNIVERSAL_IDENTIFIER,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  type: FieldType.RELATION,
  name: 'enrichmentJobs',
  label: 'Enrichment Jobs',
  icon: 'IconWand',
  relationTargetObjectMetadataUniversalIdentifier: ENRICHMENT_JOB_OBJECT_UNIVERSAL_IDENTIFIER,
  relationTargetFieldMetadataUniversalIdentifier: ENRICHMENT_JOB_COMPANY_FIELD_UNIVERSAL_IDENTIFIER,
  universalSettings: {
    relationType: RelationType.ONE_TO_MANY,
  },
});
