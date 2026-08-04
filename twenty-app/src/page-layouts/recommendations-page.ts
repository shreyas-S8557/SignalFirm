import { definePageLayout, PageLayoutTabLayoutMode } from 'twenty-sdk/define';

import {
  RECOMMENDATIONS_STANDALONE_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER,
  RECOMMENDATIONS_PAGE_TAB_UNIVERSAL_IDENTIFIER,
  RECOMMENDATIONS_PAGE_TAB_WIDGET_UNIVERSAL_IDENTIFIER,
  RECOMMENDATIONS_WIDGET_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

/**
 * Unlike the three company-*/person-conversation tab files (which extend
 * a *standard* Twenty layout via definePageLayoutTab), this app owns this
 * entire layout -- a workspace-wide dashboard isn't scoped to any one
 * object's record page, so definePageLayout with type STANDALONE_PAGE is
 * the right entity here (per docs.twenty.com/developers/extend/apps/layout:
 * "Use definePageLayout when you own the entire layout (typically a
 * RECORD_PAGE for an object you ship in your app, or a STANDALONE_PAGE)").
 *
 * KNOWN GAP: this page has no sidebar navigation item wired up yet. The
 * docs mention navigation items exist as their own entity type
 * ("Views, navigation items, and page layouts reference each other by
 * universalIdentifier"), but I could not find or verify the exact
 * `defineNavigationItem`-style API surface for it without a live
 * workspace to check against, and would rather leave this as an
 * explicit, documented gap than ship a guessed function signature that
 * might not even type-check. Until that's added, this page is reachable
 * by its direct URL once the app is synced (check your workspace's
 * developer/app settings for the generated route) rather than from the
 * sidebar.
 */

export default definePageLayout({
  universalIdentifier: RECOMMENDATIONS_STANDALONE_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER,
  name: 'Recommendations',
  type: 'STANDALONE_PAGE',
  tabs: [
    {
      universalIdentifier: RECOMMENDATIONS_PAGE_TAB_UNIVERSAL_IDENTIFIER,
      title: 'Recommendations',
      position: 0,
      icon: 'IconBulb',
      layoutMode: PageLayoutTabLayoutMode.CANVAS,
      widgets: [
        {
          universalIdentifier: RECOMMENDATIONS_PAGE_TAB_WIDGET_UNIVERSAL_IDENTIFIER,
          title: "Today's Recommendations",
          type: 'FRONT_COMPONENT',
          configuration: {
            configurationType: 'FRONT_COMPONENT',
            frontComponentUniversalIdentifier: RECOMMENDATIONS_WIDGET_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
          },
        },
      ],
    },
  ],
});
