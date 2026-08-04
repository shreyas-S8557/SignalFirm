import { definePageLayoutTab, PageLayoutTabLayoutMode } from 'twenty-sdk/define';

import {
  COMPANY_AI_INSIGHTS_PAGE_LAYOUT_TAB_UNIVERSAL_IDENTIFIER,
  COMPANY_AI_INSIGHTS_TAB_WIDGET_UNIVERSAL_IDENTIFIER,
  AI_INSIGHTS_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

/**
 * NEEDS A REAL VALUE BEFORE THIS APP CAN BE SYNCED: `definePageLayoutTab`
 * requires `pageLayoutUniversalIdentifier` to point at an *existing* page
 * layout at install time (Twenty's docs: "installation fails with a clear
 * validation error" if it doesn't resolve) -- this is the standard Company
 * record page's own universalIdentifier, and Twenty's docs show it looked
 * up per-workspace/version rather than a fixed constant exported by the
 * SDK (see docs.twenty.com/developers/extend/apps/layout's own example,
 * which hardcodes a value the same way rather than importing one). I could
 * not verify this value against a live Twenty instance in this sandbox --
 * find yours via `yarn twenty entity:list` (or your workspace's Data
 * Model settings -> Company -> record page) and replace the placeholder
 * below before running `yarn twenty app:dev` / `app:publish`.
 */
const COMPANY_RECORD_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER = 'REPLACE_WITH_YOUR_WORKSPACE_COMPANY_RECORD_PAGE_LAYOUT_ID';

export default definePageLayoutTab({
  universalIdentifier: COMPANY_AI_INSIGHTS_PAGE_LAYOUT_TAB_UNIVERSAL_IDENTIFIER,
  pageLayoutUniversalIdentifier: COMPANY_RECORD_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER,
  title: 'AI Insights',
  position: 900, // late in the tab order -- after Twenty's own built-in tabs
  icon: 'IconSparkles',
  layoutMode: PageLayoutTabLayoutMode.CANVAS,
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
