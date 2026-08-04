import { definePageLayoutTab, PageLayoutTabLayoutMode } from 'twenty-sdk/define';

import {
  PERSON_CONVERSATION_PAGE_LAYOUT_TAB_UNIVERSAL_IDENTIFIER,
  PERSON_CONVERSATION_TAB_WIDGET_UNIVERSAL_IDENTIFIER,
  CONVERSATION_PANEL_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

// Same placeholder pattern as company-ai-insights-tab.ts, targeting the
// standard Person record page instead of Company -- look this one up
// separately, it's a different layout.
const PERSON_RECORD_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER = 'REPLACE_WITH_YOUR_WORKSPACE_PERSON_RECORD_PAGE_LAYOUT_ID';

export default definePageLayoutTab({
  universalIdentifier: PERSON_CONVERSATION_PAGE_LAYOUT_TAB_UNIVERSAL_IDENTIFIER,
  pageLayoutUniversalIdentifier: PERSON_RECORD_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER,
  title: 'Conversation',
  position: 900,
  icon: 'IconMessageCircle',
  layoutMode: PageLayoutTabLayoutMode.CANVAS,
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
