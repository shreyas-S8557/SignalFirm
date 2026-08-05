import { definePageLayout } from 'twenty-sdk/define';

import {
  RECOMMENDATIONS_STANDALONE_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER,
  RECOMMENDATIONS_PAGE_TAB_UNIVERSAL_IDENTIFIER,
  RECOMMENDATIONS_PAGE_TAB_WIDGET_UNIVERSAL_IDENTIFIER,
  RECOMMENDATIONS_WIDGET_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';

/**
 * Unlike the three company/person tab files (which extend a *standard*
 * Twenty layout via definePageLayoutTab), this app owns this entire
 * layout -- a workspace-wide dashboard isn't scoped to any one object's
 * record page, so definePageLayout with type STANDALONE_PAGE is the
 * right entity here.
 *
 * The sidebar navigation item for this page lives in
 * src/navigation-items/recommendations-navigation-item.ts, using
 * defineNavigationMenuItem (Twenty SDK 2.27) with
 * type: NavigationMenuItemType.PAGE_LAYOUT, pointed at this layout's
 * universalIdentifier.
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
      // layoutMode PageLayoutTabLayoutMode.CANVAS is deprecated in 2.27 --
      // a solo full-page widget tab like this one no longer declares a
      // layoutMode; presentation is derived from the tab's widgets.
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
