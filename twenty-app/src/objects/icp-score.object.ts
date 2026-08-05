import { defineObject, FieldType, NumberDataType, ObjectOpenRecordIn } from 'twenty-sdk/define';

import {
  ICP_SCORE_OBJECT_UNIVERSAL_IDENTIFIER,
  ICP_SCORE_VALUE_FIELD_UNIVERSAL_IDENTIFIER,
  ICP_SCORE_PRIORITY_FIELD_UNIVERSAL_IDENTIFIER,
  ICP_SCORE_REASONING_FIELD_UNIVERSAL_IDENTIFIER,
  ICP_SCORE_CONFIDENCE_FIELD_UNIVERSAL_IDENTIFIER,
  ICP_SCORE_RUBRIC_VERSION_FIELD_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

/**
 * Not written to by this milestone's code -- scaffolded now for the same
 * reason as EnrichmentJob (see that file's comment). One record per scoring
 * run, so a company's ICP score history is preserved rather than
 * overwritten every re-score; `Company.latestIcpScore` (see
 * company-icp-score-badge.field.ts) is the denormalized "current value" for
 * list views and sorting.
 */
enum ICPPriority {
  HIGH = 'HIGH',
  MEDIUM = 'MEDIUM',
  LOW = 'LOW',
}

export default defineObject({
  universalIdentifier: ICP_SCORE_OBJECT_UNIVERSAL_IDENTIFIER,
  nameSingular: 'icpScore',
  namePlural: 'icpScores',
  labelSingular: 'ICP Score',
  labelPlural: 'ICP Scores',
  description: 'One ICP scoring run for a Company, scored against the weighted rubric.',
  icon: 'IconTarget',
  openRecordIn: ObjectOpenRecordIn.SIDE_PANEL,
  fields: [
    {
      universalIdentifier: ICP_SCORE_VALUE_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'score',
      type: FieldType.NUMBER,
      label: 'Score',
      icon: 'IconGauge',
      description: '0-100, computed deterministically from the rubric weights -- never an LLM-emitted number directly.',
      universalSettings: { dataType: NumberDataType.FLOAT },
      isNullable: false,
      defaultValue: 0,
    },
    {
      universalIdentifier: ICP_SCORE_PRIORITY_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'priority',
      type: FieldType.SELECT,
      label: 'Priority',
      icon: 'IconFlag',
      defaultValue: `'${ICPPriority.LOW}'`,
      options: [
        { value: ICPPriority.HIGH, label: 'High', position: 0, color: 'red' },
        { value: ICPPriority.MEDIUM, label: 'Medium', position: 1, color: 'yellow' },
        { value: ICPPriority.LOW, label: 'Low', position: 2, color: 'gray' },
      ],
    },
    {
      universalIdentifier: ICP_SCORE_REASONING_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'reasoning',
      type: FieldType.RICH_TEXT,
      label: 'Reasoning',
      icon: 'IconNotes',
      isNullable: true,
    },
    {
      universalIdentifier: ICP_SCORE_CONFIDENCE_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'confidence',
      type: FieldType.NUMBER,
      label: 'Confidence',
      icon: 'IconGauge',
      universalSettings: { dataType: NumberDataType.FLOAT },
      isNullable: false,
      defaultValue: 0,
    },
    {
      universalIdentifier: ICP_SCORE_RUBRIC_VERSION_FIELD_UNIVERSAL_IDENTIFIER,
      name: 'rubricVersion',
      type: FieldType.TEXT,
      label: 'Rubric version',
      icon: 'IconVersions',
      description: 'Which version of data/icp_rubric.yaml produced this score, for auditability when weights change.',
      isNullable: true,
    },
  ],
});
