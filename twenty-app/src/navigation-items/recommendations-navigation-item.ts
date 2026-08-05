import { defineNavigationMenuItem, NavigationMenuItemType } from 'twenty-sdk/define';

import {
  RECOMMENDATIONS_NAVIGATION_ITEM_UNIVERSAL_IDENTIFIER,
  RECOMMENDATIONS_STANDALONE_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

/**
 * Sidebar entry for the standalone Recommendations dashboard
 * (see page-layouts/recommendations-page.ts). Previously a documented
 * gap in this app -- Twenty SDK 2.27 now exposes defineNavigationMenuItem
 * with a PAGE_LAYOUT item type for exactly this case.
 */
export default defineNavigationMenuItem({
  universalIdentifier: RECOMMENDATIONS_NAVIGATION_ITEM_UNIVERSAL_IDENTIFIER,
  type: NavigationMenuItemType.PAGE_LAYOUT,
  name: 'Recommendations',
  icon: 'IconBulb',
  position: 100, // after Twenty's own built-in navigation items
  pageLayoutUniversalIdentifier: RECOMMENDATIONS_STANDALONE_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER,
});
