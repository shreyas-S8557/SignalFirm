import { definePageLayoutTab, STANDARD_PAGE_LAYOUT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import {
  COMPANY_AI_INSIGHTS_PAGE_LAYOUT_TAB_UNIVERSAL_IDENTIFIER,
  COMPANY_AI_INSIGHTS_TAB_WIDGET_UNIVERSAL_IDENTIFIER,
  AI_INSIGHTS_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

/**
 * Twenty SDK 2.27 now exports STANDARD_PAGE_LAYOUT_UNIVERSAL_IDENTIFIERS,
 * a fixed set of universalIdentifiers for every built-in page layout
 * (the same value on every workspace/version), so the standard Company
 * record page no longer needs to be looked up or hardcoded per-workspace
 * as the previous SDK required.
 */
export default definePageLayoutTab({
  universalIdentifier: COMPANY_AI_INSIGHTS_PAGE_LAYOUT_TAB_UNIVERSAL_IDENTIFIER,
  pageLayoutUniversalIdentifier: STANDARD_PAGE_LAYOUT_UNIVERSAL_IDENTIFIERS.companyRecordPage.universalIdentifier,
  title: 'AI Insights',
  position: 900, // late in the tab order -- after Twenty's own built-in tabs
  icon: 'IconSparkles',
  // layoutMode: PageLayoutTabLayoutMode.CANVAS is deprecated in 2.27 -- a
  // single full-page front-component tab like this one no longer declares
  // a layoutMode at all; presentation (solo vs stack) is now derived from
  // the tab's widgets.
  widgets: [
    {
      universalIdentifier: COMPANY_AI_INSIGHTS_TAB_WIDGET_UNIVERSAL_IDENTIFIER,
      title: 'AI Insights',
      type: 'FRONT_COMPONENT',
      configuration: {
        configurationType: 'FRONT_COMPONENT',
        frontComponentUniversalIdentifier: AI_INSIGHTS_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
      },
    },
  ],
});
