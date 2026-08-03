import {
  defineField,
  FieldType,
  RelationType,
  STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS,
} from 'twenty-sdk/define';

import {
  ICP_SCORE_OBJECT_UNIVERSAL_IDENTIFIER,
  ICP_SCORE_COMPANY_FIELD_UNIVERSAL_IDENTIFIER,
  COMPANY_ICP_SCORES_FIELD_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

export default defineField({
  universalIdentifier: COMPANY_ICP_SCORES_FIELD_UNIVERSAL_IDENTIFIER,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  type: FieldType.RELATION,
  name: 'icpScores',
  label: 'ICP Scores',
  icon: 'IconTarget',
  relationTargetObjectMetadataUniversalIdentifier: ICP_SCORE_OBJECT_UNIVERSAL_IDENTIFIER,
  relationTargetFieldMetadataUniversalIdentifier: ICP_SCORE_COMPANY_FIELD_UNIVERSAL_IDENTIFIER,
  universalSettings: {
    relationType: RelationType.ONE_TO_MANY,
  },
});
