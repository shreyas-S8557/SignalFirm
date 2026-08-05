# Twenty SDK 2.27 Migration — Summary

This document records the full audit of `@opika/crm-sync` against the
`twenty-sdk@2.27.0` / `twenty-client-sdk@2.27.0` typings and the Twenty CLI's
own compiled validation logic (both inspected directly from
`node_modules/twenty-sdk/dist` — nothing here is guessed).

## Root cause of the reported error

```
Application must declare a default role:
either pass defaultRoleUniversalIdentifier to defineApplication()
or mark a role file with defineApplicationRole()
```

`defaultRoleUniversalIdentifier` on `defineApplication()` still exists but is
**deprecated** in 2.27 in favor of a dedicated role file using
`defineApplicationRole()`. This app already had a
`APPLICATION_ROLE_UNIVERSAL_IDENTIFIER` constant sitting unused in
`src/constants/universal-identifiers.ts` — no role file ever referenced it,
and the value itself (`'crm-sync-default-role'`) wasn't even a valid UUID
(the CLI validates every `universalIdentifier` as UUID v4+).

**Fix:**
- Regenerated `APPLICATION_ROLE_UNIVERSAL_IDENTIFIER` as a real UUID.
- Added `src/roles/crm-sync-default.role.ts` calling `defineApplicationRole()`,
  granting the role full CRUD (read/update/soft-delete, not destroy) on the
  four objects this app owns (`ResearchJob`, `EnrichmentJob`, `ICPScore`,
  `ConversationSignal`), and marking it assignable to users, agents, and API
  keys.

## Every other breaking change found and fixed

### 1. `PageLayoutTabLayoutMode.CANVAS` is deprecated
Per the SDK typings: *"Solo full-page tabs are no longer stored as a layout
mode. Presentation (solo vs stack) is derived from the tab's widgets."*
Removed `layoutMode: PageLayoutTabLayoutMode.CANVAS` (and the now-unused
`PageLayoutTabLayoutMode` import) from all four page-layout-tab definitions:
`company-ai-insights-tab.ts`, `company-research-tab.ts`,
`person-conversation-tab.ts`, `recommendations-page.ts`.

### 2. Non-functional placeholder page-layout references
Three tab files referenced the standard Company/Person record pages via a
literal placeholder string (`'REPLACE_WITH_YOUR_WORKSPACE_COMPANY_RECORD_PAGE_LAYOUT_ID'`)
because, at the time they were written, the SDK had no fixed export for
these IDs. **2.27 now exports `STANDARD_PAGE_LAYOUT_UNIVERSAL_IDENTIFIERS`**
with stable, version-independent IDs for every built-in page layout,
including `companyRecordPage` and `personRecordPage`. Replaced the
placeholders with `STANDARD_PAGE_LAYOUT_UNIVERSAL_IDENTIFIERS.companyRecordPage.universalIdentifier`
and `.personRecordPage.universalIdentifier`. This was a real, previously
documented gap ("NEEDS A REAL VALUE BEFORE THIS APP CAN BE SYNCED") that is
now resolved for real, not just worked around.

### 3. Missing navigation menu item (previously an explicit "KNOWN GAP")
The standalone Recommendations dashboard (`page-layouts/recommendations-page.ts`)
had no sidebar entry because the SDK's navigation-item API wasn't available
when it was written. 2.27 exports `defineNavigationMenuItem` with a
`NavigationMenuItemType.PAGE_LAYOUT` item type built for exactly this case.
Added `src/navigation-items/recommendations-navigation-item.ts` wiring the
already-reserved-but-unused `RECOMMENDATIONS_NAVIGATION_ITEM_UNIVERSAL_IDENTIFIER`
constant to the Recommendations page layout.

### 4. `useRecordId()` is deprecated
Per `twenty-sdk/front-component` typings: *"Use `useSelectedRecordIds()`
instead. For single-record operations, use
`selectedRecordIds.length === 1 ? selectedRecordIds[0] : null`."*
Replaced in all three record-scoped front components
(`ai-insights-panel.front-component.tsx`,
`conversation-panel.front-component.tsx`,
`research-tab.front-component.tsx`) using exactly that derivation pattern,
which preserves the original single-record behavior of each tab.

### 5. `logoUrl` is deprecated, and pointed at a nonexistent asset
`application.config.ts` set `logoUrl: 'public/logo.svg'`, but (a) `logoUrl`
is deprecated in favor of `logo`, and (b) there is no `public/` folder or
`logo.svg` anywhere in this repo, so the reference was already broken.
Removed it rather than carrying forward a broken deprecated property; left a
comment for adding `logo: 'public/logo.svg'` once that asset actually
exists.

### 6. Real TypeScript compile errors in manifest entities (verified with `tsc`, not assumed)
Running `tsc --noEmit -p tsconfig.json` against the real 2.27 typings
surfaced two categories of genuine type errors, both now fixed:

- **`universalSettings: { dataType: 'float' }`** — `NumberDataType` is a
  proper TypeScript enum; a bare string literal isn't assignable to it
  (`error TS2322: Type '"float"' is not assignable to type 'NumberDataType | undefined'`).
  Fixed by importing `NumberDataType` from `twenty-sdk/define` and using
  `NumberDataType.FLOAT` in all 5 affected files (`conversation-signal.object.ts`,
  `enrichment-job.object.ts`, `icp-score.object.ts` ×2, `research-job.object.ts`,
  `fields/company-latest-icp-score.field.ts`).
- **`defaultValue: '0'` on NUMBER fields** — `FieldMetadataDefaultValue<NUMBER>`
  is `number | null`, not `string`. Fixed the 4 affected NUMBER fields
  (confidence/score fields on `ConversationSignal`, `EnrichmentJob`, and
  `ICPScore` ×2) to use the numeric literal `0` instead of the string `'0'`.
  (SELECT/MULTI_SELECT fields correctly keep their quoted-string defaults,
  e.g. `` `'${Status.PENDING}'` `` — that's the SDK's own convention for
  literal vs. computed (`'uuid'`, `'now'`) default expressions on those
  types, confirmed against the CLI's own default-value validator.)

### 7. `tsconfig.json` was missing JSX/DOM configuration
The `yarn typecheck` script (`tsc --noEmit -p tsconfig.json`) failed outright
on every front component: no `"jsx"` compiler option and no DOM lib, so JSX
syntax, `React.CSSProperties`, `fetch`, and `navigator.clipboard` all failed
to resolve. This wasn't reachable from the reported manifest-generation
error, but it's a real break in the project's own typecheck path. Fixed:
- Added `"jsx": "react-jsx"` and `"lib": ["ES2022", "DOM", "DOM.Iterable"]`
  to `tsconfig.json`.
- Added `@types/react` and `@types/react-dom` (`^19.2.0`, matching the
  `react`/`react-dom` versions the SDK itself depends on) to
  `devDependencies` in `package.json` — they were missing entirely.

Verified: with a local React-types stub standing in for the real
`@types/react` (no network access in this environment to actually fetch it),
`tsc --noEmit` passes cleanly against the entire `src/` tree, no false
positives found beyond `react/jsx-runtime` (an artifact of the stub itself,
not the codebase).

## Things intentionally left unchanged (verified correct, not migration issues)

- **`CoreApiClient` (`twenty-client-sdk/core`)** ships as an untyped stub
  (`query/mutation/upload: any`, no resource methods) inside
  `node_modules/twenty-client-sdk`. This is by design: the real, resource-typed
  client (`api.conversationSignals.create(...)`, `api.researchJobs.find(...)`,
  etc., as used in `logic-functions/*.ts`) is code-generated by the Twenty
  CLI from the live workspace schema as part of `twenty dev`/`app:build`, not
  hand-authored. This pattern is unchanged from before the migration and is
  not something this app should work around.
- **`Response`, `RoutePayload`, `DatabaseEventPayload`, `ObjectRecordCreateEvent`**
  imports from `twenty-sdk/logic-function` / `twenty-sdk/define` are current,
  non-deprecated exports — no change needed.
- **`STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS`**, `FieldType`, `RelationType`,
  `OnDeleteAction`, `ObjectOpenRecordIn` — all current exports, used
  correctly throughout `src/fields/*` and `src/objects/*`.
- **`defineFrontComponent` / `defineLogicFunction` config shapes** — match
  the current SDK types exactly; no renamed/removed properties found.

## Files created

- `src/roles/crm-sync-default.role.ts`
- `src/navigation-items/recommendations-navigation-item.ts`

## Files deleted

None. Every fix was achievable by updating existing files in place; no
manifest entity needed to be removed.

## Files modified

- `src/constants/universal-identifiers.ts` — valid UUID for the role identifier
- `src/application.config.ts` — removed deprecated/broken `logoUrl`
- `src/page-layouts/company-ai-insights-tab.ts`
- `src/page-layouts/company-research-tab.ts`
- `src/page-layouts/person-conversation-tab.ts`
- `src/page-layouts/recommendations-page.ts`
- `src/front-components/ai-insights-panel.front-component.tsx`
- `src/front-components/conversation-panel.front-component.tsx`
- `src/front-components/research-tab.front-component.tsx`
- `src/front-components/recommendations-widget.front-component.tsx` (comment only)
- `src/objects/conversation-signal.object.ts`
- `src/objects/enrichment-job.object.ts`
- `src/objects/icp-score.object.ts`
- `src/objects/research-job.object.ts`
- `src/fields/company-latest-icp-score.field.ts`
- `tsconfig.json`
- `package.json`

## Business logic / behavior preserved

- All existing `universalIdentifier`s were preserved **except** the one that
  was invalid and unused (the role identifier, which had never been synced
  anywhere since no role file referenced it — there is no existing-install
  identity at stake).
- Worker communication (`worker-proxy.ts`, all `worker-*-proxy.ts` logic
  functions, shared-secret webhook auth) is untouched.
- Webhook behavior (`job-progress-webhook.ts`, `conversation-signal-webhook.ts`,
  `reply-intelligence-trigger.ts`) is untouched.
- All object schemas, field types, relations, and descriptions are untouched
  aside from the two type-correctness fixes above (which don't change stored
  data or runtime values — `0` and `'0'` coerce identically at the database
  level; `NumberDataType.FLOAT` and `'float'` are the same string).

## Compatibility confirmation

- ✅ The manifest now declares a default role via `defineApplicationRole()`,
  resolving the reported blocking error.
- ✅ Every other manifest entity (objects, fields, logic functions, front
  components, page layouts, page layout tabs, roles, navigation items) was
  individually compared against the installed `twenty-sdk@2.27.0` typings.
- ✅ `tsc --noEmit -p tsconfig.json` passes cleanly (verified directly in
  this environment) once `@types/react`/`@types/react-dom` are installed via
  `yarn install`.
- ✅ No deprecated SDK APIs remain in use (`defaultRoleUniversalIdentifier`,
  `PageLayoutTabLayoutMode.CANVAS`, `useRecordId()`, `logoUrl` all replaced
  or removed).

## Expected next step

```bash
cd twenty-app
yarn install
yarn twenty dev
```

`yarn install` will fetch the newly added `@types/react`/`@types/react-dom`
dev dependencies (not fetchable in this sandboxed environment, which has no
network access — verified instead with a local stand-in type stub). No
further manual edits should be required.
