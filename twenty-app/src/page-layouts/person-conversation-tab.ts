import { definePageLayoutTab, STANDARD_PAGE_LAYOUT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import {
  PERSON_CONVERSATION_PAGE_LAYOUT_TAB_UNIVERSAL_IDENTIFIER,
  PERSON_CONVERSATION_TAB_WIDGET_UNIVERSAL_IDENTIFIER,
  CONVERSATION_PANEL_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

// Same fix as company-ai-insights-tab.ts, targeting the standard Person
// record page instead of Company via the SDK's fixed standard identifiers.
export default definePageLayoutTab({
  universalIdentifier: PERSON_CONVERSATION_PAGE_LAYOUT_TAB_UNIVERSAL_IDENTIFIER,
  pageLayoutUniversalIdentifier: STANDARD_PAGE_LAYOUT_UNIVERSAL_IDENTIFIERS.personRecordPage.universalIdentifier,
  title: 'Conversation',
  position: 900,
  icon: 'IconMessageCircle',
  // layoutMode CANVAS is deprecated in 2.27 -- see company-ai-insights-tab.ts.
  widgets: [
    {
      universalIdentifier: PERSON_CONVERSATION_TAB_WIDGET_UNIVERSAL_IDENTIFIER,
      title: 'Conversation',
      type: 'FRONT_COMPONENT',
      configuration: {
        configurationType: 'FRONT_COMPONENT',
        frontComponentUniversalIdentifier: CONVERSATION_PANEL_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
      },
    },
  ],
});
