import { definePageLayoutTab, STANDARD_PAGE_LAYOUT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import {
  COMPANY_RESEARCH_PAGE_LAYOUT_TAB_UNIVERSAL_IDENTIFIER,
  COMPANY_RESEARCH_TAB_WIDGET_UNIVERSAL_IDENTIFIER,
  RESEARCH_TAB_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

// See company-ai-insights-tab.ts's comment -- same fix, both tabs target
// the same Company record page via the SDK's fixed standard identifiers.
export default definePageLayoutTab({
  universalIdentifier: COMPANY_RESEARCH_PAGE_LAYOUT_TAB_UNIVERSAL_IDENTIFIER,
  pageLayoutUniversalIdentifier: STANDARD_PAGE_LAYOUT_UNIVERSAL_IDENTIFIERS.companyRecordPage.universalIdentifier,
  title: 'Research',
  position: 901,
  icon: 'IconSearch',
  // See company-ai-insights-tab.ts's comment -- layoutMode CANVAS is
  // deprecated in 2.27 and no longer needed for a solo widget tab.
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
