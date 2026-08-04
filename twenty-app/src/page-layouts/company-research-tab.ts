import { definePageLayoutTab, PageLayoutTabLayoutMode } from 'twenty-sdk/define';

import {
  COMPANY_RESEARCH_PAGE_LAYOUT_TAB_UNIVERSAL_IDENTIFIER,
  COMPANY_RESEARCH_TAB_WIDGET_UNIVERSAL_IDENTIFIER,
  RESEARCH_TAB_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

// See company-ai-insights-tab.ts's comment -- same placeholder, same fix
// needed before sync (both tabs target the same Company record page).
const COMPANY_RECORD_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER = 'REPLACE_WITH_YOUR_WORKSPACE_COMPANY_RECORD_PAGE_LAYOUT_ID';

export default definePageLayoutTab({
  universalIdentifier: COMPANY_RESEARCH_PAGE_LAYOUT_TAB_UNIVERSAL_IDENTIFIER,
  pageLayoutUniversalIdentifier: COMPANY_RECORD_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER,
  title: 'Research',
  position: 901,
  icon: 'IconSearch',
  layoutMode: PageLayoutTabLayoutMode.CANVAS,
  widgets: [
    {
      universalIdentifier: COMPANY_RESEARCH_TAB_WIDGET_UNIVERSAL_IDENTIFIER,
      title: 'Research',
      type: 'FRONT_COMPONENT',
      configuration: {
        configurationType: 'FRONT_COMPONENT',
        frontComponentUniversalIdentifier: RESEARCH_TAB_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
      },
    },
  ],
});
