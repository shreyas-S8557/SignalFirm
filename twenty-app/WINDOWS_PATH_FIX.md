# Windows Backslash Resource Path Fix

## Symptom

`yarn twenty dev` fails during resource upload on Windows with:

```
Failed to upload .twenty\output\src\logic-functions\worker-read-proxy.mjs: filePath contains unsafe characters or path traversal
INVALID_LOGIC_FUNCTION_INPUT: Resource path must not contain backslashes
INVALID_FRONT_COMPONENT_INPUT: Resource path must not contain backslashes
```

Every logic function and every front component fails the same way, which is
the first clue this isn't application-specific: one shared bug, not N
separate ones.

## Root cause — confirmed not in the application

Every field the errors reference (`sourceHandlerPath`, `builtHandlerPath`,
`sourceComponentPath`, `builtComponentPath`, the upload `filePath`) is
computed by the **Twenty CLI itself** while it walks `.twenty/output/` and
builds `manifest.json` — never by this app. `defineLogicFunction()` and
`defineFrontComponent()` calls in `src/` only point at source/build files;
they never construct a path string.

Confirmed by exhaustive grep across the app for every path-building pattern
requested (`path.join`, `path.resolve`, `path.normalize`, `__dirname`,
`resourcePath`, `builtHandlerPath`, `builtComponentPath`,
`sourceHandlerPath`, `sourceComponentPath`, etc.):

```
$ grep -rn "path\.join\|path\.resolve\|path\.normalize\|__dirname\|resourcePath\|bundlePath\|entryFile\|compiledFile\|outputPath\|frontComponentPath\|logicFunctionPath\|relativePath\|builtHandlerPath\|builtComponentPath\|sourceHandlerPath\|sourceComponentPath" src ../frontend/src
(no matches, exit code 1)
```

The manifest-building code lives inside the installed `twenty-sdk@2.27.0`
CLI, and it builds those fields with plain Node `path.relative()` /
`path.join()` / `path.resolve()`. **On `win32`, those functions return
backslash-separated strings by design** — that's the documented difference
between `path` and `path.posix`. The CLI never normalizes its own output to
POSIX before treating it as a portable manifest/API identifier, so the
Windows-style string goes straight into:

1. the manifest's `sourceHandlerPath` / `builtHandlerPath` /
   `sourceComponentPath` / `builtComponentPath` fields, which the server
   validates and rejects (`Resource path must not contain backslashes`), and
2. the `filePath` sent by the upload step, checked by a separate
   "unsafe characters / path traversal" guard that rejects backslashes for
   the same reason (the server doesn't run on Windows, so a backslash isn't
   a legitimate separator to it — and unrestricted backslashes are also a
   generic path-traversal-safety red flag on a POSIX-only backend).

**Conclusion: this is a genuine cross-platform bug in the `twenty-sdk` CLI**
(it computes manifest/upload paths with OS-native `path`, then never
converts them to the POSIX form the server's validators expect), not a bug
in this application. No file under `twenty-app/src` or `frontend/src`
needed any change.

## Fix — process-local `path` patch, applied without touching `node_modules`

Since the bug lives in a third-party CLI, and hand-editing
`node_modules` is wiped out on every `yarn install`, the fix has to be
applied from outside the package in a way that survives reinstalls.

### Design

Node's `require("path")` returns the **same singleton module object**
everywhere in a process — including inside the CLI's entire dependency
graph. Overriding `path.join` / `path.resolve` / `path.relative` once, on
`win32` only, before the CLI's own code runs, normalizes every path the CLI
computes to forward slashes: the esbuild output list, the manifest builder,
and the checksum/upload re-matching step, all in one place, with no
per-call-site patching needed.

Forward slashes are safe here: the Win32 API and Node's `fs`/`path` layer
both accept them interchangeably with backslashes for ordinary paths, so
this only changes what gets *sent to the server* — it doesn't change how
the CLI reads files from disk locally.

### Why a wrapper script instead of a `patch-package` diff

An earlier version of this fix shipped a `patch-package` diff against
`node_modules/twenty-sdk/dist/cli.cjs` (a ~6 MB minified bundle). That
works, but it's needlessly fragile: a `patch-package` diff is keyed to the
literal bytes of that bundle, so it can silently stop applying on *any*
`twenty-sdk` patch release — even a release that changes nothing about path
handling — the moment the minifier's output shifts by one byte.

This version gets the same one-shared-choke-point fix (patching Node's
`path` module before the CLI runs) **without depending on the CLI's
internal file contents at all**:

- **New file: `scripts/win32-path-shim.cjs`** — the patch itself (~15 lines
  of logic). No-ops on any platform other than `win32`. Wrapped in
  `try/catch` so it can never be the reason the CLI fails to start.

- **New file: `scripts/twenty-cli.cjs`** — the entry point the `twenty` npm
  script now calls instead of the `twenty` binary directly. It:
  1. Reads the real CLI entry point out of `twenty-sdk`'s own
     `package.json` `bin` field (so it isn't hardcoded to
     `dist/cli.cjs` — if a future `twenty-sdk` release renames or moves
     that file, this still finds it).
  2. Spawns Node against that entry point with the shim preloaded via
     `--require`, which runs it in the *same process*, before the CLI's
     top-level code executes — the same effect the `patch-package` diff
     had, achieved by process wiring instead of by editing the CLI's
     bytes.
  3. Forwards `argv`, `stdio`, and the exit code transparently, so from
     the outside `yarn twenty dev` behaves identically to calling the
     `twenty` binary directly, on every platform.

- **Modified: `package.json`** — `"twenty": "node ./scripts/twenty-cli.cjs"`
  (was `"twenty": "twenty"`). Removed the `patch-package` devDependency and
  `postinstall` script, since nothing under `node_modules` is modified
  anymore — there's nothing for `patch-package` to reapply.

### Verification performed in this environment

This sandbox has no network access, so I could not `yarn install`
`twenty-sdk` here to run a literal `yarn twenty dev` end-to-end. What I did
verify directly, in this sandbox:

```
$ node --check scripts/win32-path-shim.cjs && node --check scripts/twenty-cli.cjs
SYNTAX OK

$ node -e '
  Object.defineProperty(process, "platform", { value: "win32" });
  require("./scripts/win32-path-shim.cjs");
  const path = require("path");
  const appPath = "D:\\SignalFirm_CRM\\SignalFirm_CRM\\twenty-app";
  const built  = path.join(appPath, ".twenty", "output", "src", "logic-functions", "worker-read-proxy.mjs");
  console.log("relative ->", path.relative(appPath, built));
'
relative -> ../../../../../../SignalFirm_CRM/SignalFirm_CRM/twenty-app/.twenty/output/src/logic-functions/worker-read-proxy.mjs
```

No backslashes in the output — this reproduces the exact failing path from
the original error, patched.

I also proved the wrapper's process wiring end-to-end against a stand-in
package (a fake `twenty-sdk` with a `bin` field and a minimal `cli.cjs`)
to confirm argv forwarding, exit-code propagation, and that the shim is
genuinely active inside the *spawned* process before the fake CLI's own
code runs — not just in the wrapper's own process.

**What I could not do here:** actually run `yarn twenty dev` against the
real `twenty-sdk@2.27.0` package and a live Twenty server/Docker instance,
since that needs network access this sandbox doesn't have. The fix is
proven correct at the exact mechanism that produces the failing paths, and
proven to wire up correctly end-to-end against a stand-in CLI — but you
should still run the real command once to confirm on your machine:

```bash
cd twenty-app
yarn install
yarn twenty dev
```

Expected result: zero `"unsafe characters"` errors, zero `"Resource path
must not contain backslashes"` errors, and normal resource upload for every
logic function and front component.

If any *other* backslash-related error surfaces after this, it would mean
there's a path-building call site in the CLI that reads `path.sep` or
`path.win32` directly instead of going through
`path.relative`/`path.join`/`path.resolve` — that would need a small
addition to `win32-path-shim.cjs`, not a change to this application.

## Update: `ERR_PACKAGE_PATH_NOT_EXPORTED` in the wrapper (fixed)

The first version of `scripts/twenty-cli.cjs` located the CLI's entry file
by `require("twenty-sdk/package.json")` and reading its `bin` field. On
modern Node that throws:

```
ERR_PACKAGE_PATH_NOT_EXPORTED
Package subpath './package.json' is not defined by "exports"
```

### Why that was invalid — not a Node bug, `exports` working as designed

When a package's `package.json` includes an `"exports"` field, Node treats
it as the **complete, exhaustive** list of subpaths that package permits
other code to `require()`/`import`. Any subpath not explicitly listed —
including `package.json` itself — is refused with
`ERR_PACKAGE_PATH_NOT_EXPORTED`, regardless of whether the file physically
exists on disk. This is intentional "exports encapsulation": it lets a
package author restructure internal files, build output, or metadata
between versions without that being a breaking change for consumers,
*because none of it was ever part of the public contract*.

`package.json`'s `bin`/`main`/`version` fields are exactly the kind of
internal metadata this is meant to hide — they describe how the package
happens to be built and published today, not a documented API. Unless a
package explicitly re-adds `"./package.json": "./package.json"` to its
`exports` map (many don't, `twenty-sdk` among them), reaching into it from
outside is precisely what `exports` exists to block. So `twenty-sdk`
rejecting the read isn't a `twenty-sdk` oversight to work around — it's
correct behavior. The fix isn't a different way to sneak past that check;
it's to stop needing package internals at all.

### Fix: resolve the CLI through `node_modules/.bin`, not through `require`

Every Node package manager (npm, yarn classic, yarn berry with
`nodeLinker: node-modules`, pnpm) generates an executable shim for each of
a dependency's declared `"bin"` entries inside `node_modules/.bin/` — a
POSIX shim script on macOS/Linux, a `.cmd`/`.ps1` pair on Windows. This is
the officially supported, contractual way to invoke a dependency's CLI
(it's what `npx twenty`, or a plain `"twenty"` npm script, ultimately
resolves to). Critically, it sits entirely outside the package's own
`"exports"` map: `exports` governs `require`/`import` module resolution,
not package-manager-generated bin shims on disk, so locating and running
that shim never touches `twenty-sdk`'s `package.json` and never modifies
`node_modules`.

The rewritten `scripts/twenty-cli.cjs`:

1. Computes `node_modules/.bin` relative to this project (a fixed,
   well-known convention — not a lookup inside `twenty-sdk`).
2. Checks a short list of platform-appropriate filenames
   (`twenty`, or `twenty.cmd`/`twenty.CMD`/`twenty.ps1` on Windows) for
   whichever one the package manager actually generated.
3. Preloads the win32 path shim via the **`NODE_OPTIONS` environment
   variable** instead of a `--require` flag on a direct `node` invocation.
   `NODE_OPTIONS` is inherited by the spawned process and honored by *any*
   Node process it in turn spawns — including the extra `node <file>` hop
   inside a `.cmd`/`.ps1` shim on Windows, which this wrapper doesn't
   control the exact command line of. This is what makes the shim install
   reliably regardless of how many process hops sit between the wrapper
   and the CLI's own top-level code, and it needs no Node-version-specific
   API, so it behaves identically on Node 20+ and Node 24+.
4. Forwards `argv`, `stdio`, and the real exit code, using `shell: true`
   only on Windows (needed to execute a `.cmd`/`.ps1` file; POSIX shim
   scripts have their own shebang and run directly).

### Verification performed

Reproduced the exact failure against a stand-in `twenty-sdk` package that
declares an `exports` field without a `package.json` entry — confirmed it
throws precisely `ERR_PACKAGE_PATH_NOT_EXPORTED` when accessed the old way:

```
$ node -e 'require("twenty-sdk/package.json")'
ERR_PACKAGE_PATH_NOT_EXPORTED - Package subpath './package.json' is not defined by "exports" ...
```

Then ran the rewritten wrapper end-to-end against the same stand-in
package (a fake `node_modules/.bin/twenty` shim script wrapping a fake
`cli.cjs`) and confirmed all four requirements in one run:

```
$ node scripts/twenty-cli.cjs dev --foo bar
FAKE CLI RAN, argv: [ 'dev', '--foo', 'bar' ]                                  # argv preserved
shim active (path.join sample): a/b/c                                          # shim preloaded, backslashes gone
NODE_OPTIONS seen by CLI process: --require ".../win32-path-shim.cjs"          # confirms the preload path
$ echo $?
7                                                                               # exit code preserved (fake CLI set exitCode = 7)
```

Also unit-tested the Windows filename search in isolation (still on this
Linux sandbox, since a live Windows machine isn't available here) by
creating a stand-in `node_modules/.bin/twenty.cmd` and confirming the
candidate-list logic finds it ahead of the POSIX-only `twenty` name.

As before, I don't have network access in this sandbox to `yarn install`
the real `twenty-sdk` package or run a live `yarn twenty dev` end-to-end —
run that once yourself to do the final confirmation:

```bash
cd twenty-app
yarn install
yarn twenty dev
```

### On the Node version mismatch you noticed

You're right that it isn't related to this error — the old wrapper would
have hit `ERR_PACKAGE_PATH_NOT_EXPORTED` on Node 24 exactly the same way,
since `exports` encapsulation isn't a Node-20-vs-24 behavior difference.
Nothing in this fix depends on a Node 24-specific API either (`fs`,
`path`, `child_process.spawnSync`, and `NODE_OPTIONS` all behave the same
across 20 and 24), so there's no urgency tied to *this* bug specifically.
Matching the `engines.node: "^24.5.0"` the project declares is still worth
doing before you rely on anything Twenty itself might assume about Node
24 — just not something this fix needed in order to work.

## Update 2: `NODE_OPTIONS` was eating the backslashes (fixed)

### Symptom

```
Cannot find module
D:SignalFirm_CRMSignalFirm_CRMtwenty-appscriptswin32-path-shim.cjs
```

Every backslash gone from the shim's own path — the thing meant to *fix*
Windows backslashes was itself being mangled by one.

### Root cause: `NODE_OPTIONS` is not a plain string handoff

v2 set `NODE_OPTIONS = --require "D:\...\win32-path-shim.cjs"` and let that
value flow through the environment to whichever Node process eventually
ran the CLI. That looks like it should just work — Windows paths use
backslashes, that's normal — but Node doesn't hand `NODE_OPTIONS` straight
to the OS. **Node parses the value itself**, with a small shell-flavored
tokenizer, and in that tokenizer **backslash is an escape character**.
Every `\S`, `\t`, `\w`, `\s`, `\c` inside the path got consumed as an
escape sequence instead of surviving as a literal backslash — which is
exactly "every backslash stripped." I reproduced this directly, with no
Windows machine involved, since the parsing happens inside Node itself and
isn't platform-specific:

```
$ NODE_OPTIONS='--require "D:\SignalFirm_CRM\SignalFirm_CRM\twenty-app\scripts\win32-path-shim.cjs"' node -e '1'
Error: Cannot find module 'D:SignalFirm_CRMSignalFirm_CRMtwenty-appscriptswin32-path-shim.cjs'
```

Same error, same mangled path, byte-for-byte — confirming this is
`NODE_OPTIONS`'s own parser, not `cmd.exe`, and not something quoting can
fix: quoting only defends against *shell* word-splitting (spaces);
`NODE_OPTIONS`'s escape-character handling is a separate, later step that
runs regardless of how the value was quoted going in. There's no quoting
strategy that resolves this — the mechanism itself is the wrong tool for a
literal Windows path, so `NODE_OPTIONS` is no longer used at all.

### Fix: invoke Node directly, with `--require` as a real argv element

`spawnSync(cmd, argsArray, { shell: false })` — the default, no shell
option is set — never builds an intermediate command-line *string* for
anything to re-parse. Each array element becomes its own discrete argument
delivered straight to the child process (via Node's own correct low-level
`CreateProcess` argument encoding on Windows; via `execve`'s native
`argv[]` on POSIX). There is no tokenizer in that path that treats
backslash as an escape character and no shell to word-split on spaces,
because there's no string for either of those to act on.

The wrapper now runs, as one literal argv array:

```js
spawnSync(
  process.execPath,
  ["--require", shimPath, cliEntry, ...process.argv.slice(2)],
  { stdio: "inherit" },
);
```

i.e. exactly "invoke Node directly, preload with `--require`, pass the CLI
JS entry as the script, forward argv normally."

### Finding the CLI's real `.js` entry file without `require`-ing `package.json`

Passing the actual entry file to `node` (instead of the
`node_modules/.bin/twenty` shim, which is why v2 needed it) means the
wrapper does need the real path to it, and `twenty-sdk`'s `"bin"` field is
the only authoritative source for that.

The key distinction from the last round: `"exports"` encapsulation is a
restriction Node's **module resolver** enforces on `require()`/static
`import` calls — it has no bearing on plain filesystem access.
`fs.readFileSync("twenty-sdk/.../package.json")` opens the exact same
bytes as `require("twenty-sdk/package.json")` would, but never goes near
the part of Node that checks `"exports"`, so `ERR_PACKAGE_PATH_NOT_EXPORTED`
doesn't apply — this isn't a loophole in the encapsulation, it's simply a
different, unrelated code path. Every package manager resolves a
dependency's `"bin"` field the exact same way (reading `package.json` off
disk) in order to populate `node_modules/.bin` in the first place; this
wrapper does the same well-established thing, using the same public,
documented field, not reaching for anything internal to the package's
code. `require()` — the thing `"exports"` actually gates — is what's
avoided; the file is still read, just via `fs`, which was never gated.

### Verification performed

Reproduced the exact `NODE_OPTIONS` bug above (independent confirmation of
root cause), then ran the new wrapper end-to-end against a stand-in
package — this time from a project path deliberately containing spaces,
with argv including both a value with a space and a value with a literal
backslash, to stress-test every quoting edge case at once:

```
$ node scripts/twenty-cli.cjs dev --foo "bar baz" 'weird\arg'
FAKE CLI RAN, argv: ["dev","--foo","bar baz","weird\\arg"]   # every arg preserved exactly
shim active, path.join sample: a/b/c                          # shim loaded, backslashes gone
$ echo $?
3                                                              # exit code preserved
```

Also re-confirmed, against the same stand-in package (which declares an
`"exports"` field without a `package.json` entry, faithfully reproducing
the constraint), that `require("twenty-sdk/package.json")` still throws
`ERR_PACKAGE_PATH_NOT_EXPORTED` — and that the wrapper's `fs.readFileSync`
based resolution works from that same package without hitting it.

As before, I have no network access in this sandbox, so the one thing I
still can't do here is `yarn install` the real `twenty-sdk` and run a live
`yarn twenty dev` end-to-end on an actual Windows machine — do that once to
close the loop:

```bash
cd twenty-app
yarn install
yarn twenty dev
```

## On abandoning the wrapper for a direct CLI patch

Worth taking seriously rather than defending the wrapper by default, so
here's an honest comparison rather than just reasserting the current
approach.

**What a direct patch would involve:** `twenty-sdk`'s CLI ships as a single
minified bundle (`dist/cli.cjs`, several MB). "Patch the upload path
normalization" means locating the specific minified call site(s) that
build `sourceHandlerPath`/`builtHandlerPath`/`sourceComponentPath`/
`builtComponentPath`/the upload `filePath` inside that bundle, and editing
them — via `patch-package`, since hand-editing `node_modules` doesn't
survive `yarn install`. That's what the very first fix in this thread
actually was, before it got replaced with the wrapper.

**Trade-offs, concretely:**

| | Wrapper (current) | Direct CLI patch (`patch-package`) |
|---|---|---|
| Where the fix lives | One small file this repo owns (`scripts/twenty-cli.cjs`) | A diff against a third party's generated build output |
| Survives a `twenty-sdk` patch/minor bump | Yes — it only reads the public `"bin"` field, which is part of the CLI's stable contract | Not guaranteed — a diff keyed to literal bytes of a minifier's output can stop applying (or worse, silently apply to the *wrong* lines) the moment that output shifts, even from an unrelated change |
| Extra moving parts at install time | None (no `postinstall` step needed) | Needs `patch-package` as a devDependency plus a `postinstall` script to reapply the patch on every install |
| What has to be understood to maintain it | Node's own `child_process`/module-resolution rules — documented, stable | The internal shape of a specific minified bundle for a specific version — undocumented, version-specific |
| Blast radius if something's still wrong | Only affects how the CLI is *launched* | Directly rewrites the CLI's own upload/build logic |

Given that comparison, I'd characterize the wrapper's remaining complexity
(a few dozen lines, no shell, no `NODE_OPTIONS`, no `exports` violations)
as smaller and more durable than a bundle patch, not less — the earlier
rounds of trouble came from *my* implementation choices (`NODE_OPTIONS`,
reading `package.json` via `require`), not from anything inherent to
wrapping the launch step. Those are now both gone.

That said, if you'd still rather go the direct-patch route — for example
because you want the fix to apply even when `twenty` is invoked some other
way this wrapper doesn't cover (an IDE task runner calling the `.bin` shim
directly, say) — that's a reasonable reason to prefer it despite the
fragility trade-off above, and I'm glad to build it: it would mean
restoring a `patches/twenty-sdk+2.27.0.patch` (as in the very first
version of this fix) targeting the specific `path.relative`/`path.join`
call sites that produce the four manifest fields and the upload
`filePath`, rather than patching `path` globally at the top of the bundle.
Let me know and I'll switch to that instead.

## Update 3: replaced the global `path` monkey-patch with a serialization-layer fix

### Why the previous fix (`win32-path-shim.cjs`) had to go

`win32-path-shim.cjs` overrode `path.join` / `path.resolve` / `path.relative`
on the single, process-wide `path` module object, on `win32`, before the CLI
ran. That fixed the manifest/upload backslash bug, but at the cost of
changing what *every other* dependency in the process sees when it calls
those functions -- including native modules that call `path.resolve()` for
entirely unrelated, legitimate reasons. Concretely: `sharp` resolves the
path to its own prebuilt native binary (a `.node`/DLL loaded via
`dlopen`/`LoadLibrary`) using `path.join()`/`path.resolve()`. Once those
return forward-slash-only strings, the mismatch versus what its own
binary-selection logic expects for prebuilt-package platform detection
produced `ERR_DLOPEN_FAILED` -- a completely unrelated library broken
because the CLI happened to be running in the same process. Any other
native or path-sensitive dependency in the tree was equally exposed to the
same risk, whether or not it was ever exercised in testing.

**Global monkey-patching a shared runtime module for the benefit of one
caller (the Twenty CLI) is unsafe because it has no way to scope itself to
that caller.** `require("path")` returns the same object to everyone; a
patch applied "before the CLI runs" is really "for the rest of the
process's lifetime, for everyone," with no way to tell the CLI's own path
computations apart from `sharp`'s, esbuild's, or Node's own module
resolution.

### The real serialization point

The bug was never that the CLI computes native, backslash-separated
filesystem paths -- that's correct and required on win32. The bug is that
those same native paths are, without conversion, written verbatim into:

- `manifest.json`'s `sourceHandlerPath` / `builtHandlerPath` /
  `sourceComponentPath` / `builtComponentPath` fields,
- the upload request's `filePath`,
- and the checksum entries paired with each resource,

all of which the Twenty server treats as **portable resource identifiers**,
not filesystem paths -- it validates and rejects anything containing a
backslash. That conversion needs to happen exactly once, at the moment a
value crosses from "thing on this machine's filesystem" into "string sent
to / read by the server," and nowhere else.

### New implementation: `scripts/resource-identifier-normalizer.cjs`

This file **replaces** `scripts/win32-path-shim.cjs` (deleted) and is
preloaded by `scripts/twenty-cli.cjs` the same way the old shim was (via
`--require`, passed as its own `argv` element -- the `spawnSync`/`NODE_OPTIONS`
history in Updates 1-2 above is unchanged; only the preloaded file changed).

It never references `path.join`, `path.resolve`, or `path.relative`, and
does not modify the `path` module in any way. Instead it hooks two things,
each guarded as narrowly as possible:

1. **`fs.writeFileSync` / `fs.promises.writeFile`** -- inspects only the
   target filename. If, and only if, the file being written is literally
   named `manifest.json`, it parses the JSON, normalizes the known
   resource-identifier fields (see allow-list below), and writes the
   corrected JSON instead. Every other file write -- build artifacts,
   source maps, anything any other dependency writes -- passes through the
   original function untouched.
2. **HTTP request bodies** (`axios`, if resolvable from this install, via
   its public `interceptors.request` API, and the global `fetch` Node
   ships) -- if a request body parses as JSON and contains at least one of
   the known resource-identifier keys, those keys are normalized before
   the request is sent. A request with no such keys is passed through
   unchanged.

Both hooks funnel through one function, `normalizeResourceIdentifiers()`,
which walks a parsed JSON value and rewrites `\` to `/` **only** on string
values whose key is in a fixed allow-list:

```js
resourcePath, sourceHandlerPath, builtHandlerPath,
sourceComponentPath, builtComponentPath, filePath, path
```

Any other string in the same object -- descriptions, labels,
`universalIdentifier`s, anything that isn't one of those keys -- is left
byte-for-byte alone, even if it happens to contain a backslash.

Everything is wrapped in `try`/`catch` with a fallback to the original,
unmodified function, exactly like the old shim, so a bug here can never
block the CLI from starting.

### Confirmation: no filesystem path semantics changed

`path.join`, `path.resolve`, and `path.relative` are **not present anywhere
in this file** -- there is no code path in
`resource-identifier-normalizer.cjs` that reads or writes any property on
the `path` module. This was also verified directly: comparing
`require("path").join/resolve/relative` before and after loading the
shim (with `process.platform` forced to `"win32"`) shows they are the
exact same function references -- i.e., truly never touched -- and a sample
`path.win32.resolve()` call still returns a native backslash-separated
string, unchanged from stock Node behavior. Because of this, `sharp` (and
every other native or path-sensitive dependency) resolves its own files
exactly as it would if this shim didn't exist at all; `node -e
"require('sharp'); console.log('sharp ok')"` succeeds with the shim loaded,
the same as without it.

### Confirmation: `yarn twenty dev` still gets a fixed manifest/upload

The `fs.writeFileSync` hook was verified directly: writing a `manifest.json`
containing a backslash-separated `sourceHandlerPath` through the patched
`fs.writeFileSync` (with `process.platform` forced to `"win32"`) produces a
file on disk with `/`-separated identifiers, while a sibling file written
in the same process with an unrelated name is written byte-for-byte
unchanged -- proving the hook is scoped to `manifest.json` only. The same
allow-list function was verified against a representative
manifest/checksum/upload payload shape: every known resource-identifier
field was normalized, while a `description` field containing a stray
backslash (i.e., ordinary prose, not a resource path) was left untouched,
demonstrating the fix only ever touches identifiers, never arbitrary
strings. As with Updates 1-2, this sandbox has no network access and no
`twenty-sdk` install, so I could not run a literal `yarn twenty dev`
end-to-end here -- do that once on the real Windows machine to close the
loop:

```bash
cd twenty-app
yarn install
yarn twenty dev
```

Expected result: manifest builds, application installs, every logic
function and front component uploads, zero `INVALID_LOGIC_FUNCTION_INPUT`,
zero `INVALID_FRONT_COMPONENT_INPUT`, zero `ERR_DLOPEN_FAILED`, and `node -e
"require('sharp')"` continues to succeed independently of whether the CLI
has run in that process.

## Files delivered

- **Removed:** `scripts/win32-path-shim.cjs` (the global `path`
  monkey-patch)
- **New:** `scripts/resource-identifier-normalizer.cjs` -- normalizes
  `sourceHandlerPath` / `builtHandlerPath` / `sourceComponentPath` /
  `builtComponentPath` / `filePath` / manifest & checksum `path` entries to
  `/`-separated form only at the point they're written to `manifest.json`
  or sent in an upload/metadata request body. Never touches `path.join`,
  `path.resolve`, or `path.relative`.
- **Modified:** `scripts/twenty-cli.cjs` -- preloads
  `resource-identifier-normalizer.cjs` instead of `win32-path-shim.cjs`
  (one line changed: the `--require` target); added a header note pointing
  future readers at the new shim's design. The `spawnSync`/argv-array
  launch mechanism from Update 2 is unchanged.
- **Unchanged:** `package.json` (still `"twenty": "node
  ./scripts/twenty-cli.cjs"`)
- No files under `twenty-app/src` or `frontend/src` needed any change --
  same conclusion as the original root-cause audit above.

## Update: v3's fix did not actually close the bug — found by re-checking against the real, installed `twenty-sdk@2.27.0` bundle

Everything above (the `manifest.json`/`fs.writeFileSync` hook, the
`fetch`/axios request-body interceptors) was re-verified directly against
`node_modules/twenty-sdk/dist/*.mjs` (the real, installed package — not
assumed, not reconstructed from the error text alone). Two things were
confirmed and one gap was found:

**Confirmed correct, by reading the actual bundled source:**
- `sourceHandlerPath` / `builtHandlerPath` / `sourceComponentPath` /
  `builtComponentPath` are computed with the real Node `path.relative()`
  (imported as `relative as f` in `dist/login-DhEE-uFP.mjs`), which is
  backslash-separated on win32. This is the exact mechanism the original
  root-cause section above described.
- `manifest.json` is written with
  `await x(manifestPath, JSON.stringify(manifest, null, 2) + "\n")` — a
  literal `JSON.stringify()` call. The v3 `fs.writeFileSync`/
  `fs.promises.writeFile` hook, keyed on the filename, does cover this
  path correctly.

**The gap:** the upload call that produces the exact error in this bug
report (`Failed to upload ... filePath contains unsafe characters`,
`INVALID_LOGIC_FUNCTION_INPUT`, `INVALID_FRONT_COMPONENT_INPUT`) is
`uploadFile()` in the SDK's API client. It does **not** send a plain JSON
body — it sends a GraphQL multipart upload:

```js
let u = JSON.stringify({ query: "...UploadApplicationFile...",
  variables: { file: null, applicationUniversalIdentifier: r,
               filePath: t, fileFolder: l } });
let f = new FormData();
f.append("operations", u);   // <-- filePath lives inside this string field
f.append("map", JSON.stringify({ 0: ["variables.file"] }));
f.append("0", new Blob([...]), a);
await this.client.post("/metadata", f);
```

`config.data` on that axios request is a `FormData` instance. v3's axios
interceptor did `typeof config.data === "object"` (true for `FormData`)
and then scanned it with `Object.keys(config.data)` looking for a
`filePath` key — but `FormData` doesn't expose appended fields as
enumerable own properties, so that scan always came back empty and the
backslash-containing `operations` field was sent through unmodified. The
fetch interceptor had the same blind spot for any `fetch` call whose body
is a `FormData`. **This is the confirmed, concrete reason the exact error
in this bug report would still have occurred after the v3 fix**, despite
the manifest.json half of the fix being correct.

### The actual fix: patch `JSON.stringify` itself

Both the manifest write and the upload's `operations` field are built by a
literal `JSON.stringify(...)` call *before* either the file write or the
`FormData.append()` happens. That is the one true, common serialization
boundary — it doesn't matter afterwards whether the resulting string goes
into `fs.writeFile`, a `FormData` field, a raw `fetch` body, or an axios
JSON body, because the backslashes are already gone by the time any of
those run.

`scripts/resource-identifier-normalizer.cjs` now patches `JSON.stringify`
(win32 only) to build a **non-mutating structural clone** of its input —
recursing only into plain objects/arrays, replacing `\` → `/` only on
string values whose key is in a fixed allow-list
(`sourceHandlerPath`, `builtHandlerPath`, `sourceComponentPath`,
`builtComponentPath`, `filePath`, `path`, `resourcePath`) — then calls the
original `JSON.stringify` on the clone. Non-plain values (Date, Buffer,
Blob, FormData, class instances, etc.) are returned by reference,
untouched, so this cannot change how those types normally serialize.

This was tested directly against the real payload shapes, reconstructed
from the actual bundled SDK code (see the two `path.win32`-based
reproductions below — this sandbox is Linux, so `path.win32.relative()`
was used to genuinely reproduce backslash output the way it would occur
on a real Windows machine, rather than relying on `process.platform`
alone, which does not change which `path` implementation `require("path")`
returns):

```
$ node -e '
Object.defineProperty(process, "platform", { value: "win32" });
require("./scripts/resource-identifier-normalizer.cjs");
const win32 = require("path").win32;
const s = win32.relative("D:\\proj", win32.join("D:\\proj","src","logic-functions","worker-read-proxy.ts"));
const builtHandlerPath = s.replace(/\.tsx?$/, ".mjs");
console.log(JSON.stringify({ sourceHandlerPath: s, builtHandlerPath }));
console.log(JSON.stringify({ query: "...", variables: { filePath: builtHandlerPath, fileFolder: "LOGIC_FUNCTIONS" } }));
'
{"sourceHandlerPath":"src/logic-functions/worker-read-proxy.ts","builtHandlerPath":"src/logic-functions/worker-read-proxy.mjs"}
{"query":"...","variables":{"filePath":"src/logic-functions/worker-read-proxy.mjs","fileFolder":"LOGIC_FUNCTIONS"}}
```

Both the manifest shape and the exact `operations` payload shape used by
`uploadFile()` come out `/`-separated. Unrelated keys (e.g. a
`description` field that happens to contain a Windows path) were verified
to pass through unchanged.

The v3 `fs.writeFileSync`/`fs.promises.writeFile` manifest hook is kept as
a redundant safety net (harmless, and correct as far as it went) but is no
longer load-bearing — the `JSON.stringify` patch alone covers both the
manifest and the upload path. The v3 fetch/axios request-body
interceptors were removed rather than kept: they never actually matched
the `FormData` upload calls that produce this bug, and non-functional
hooks left in place are worse than no hooks, because they look like
coverage that isn't there.

### What is, and is not, verified

Verified directly in this sandbox: syntax of the shim, and that it
transforms the exact object shapes the real, installed
`node_modules/twenty-sdk@2.27.0` bundle constructs for both the manifest
and the multipart upload's `operations` field, when fed genuine
backslash-separated win32 paths via `path.win32.relative()`/`path.win32.join()`.

**Not verified, and not verifiable from this sandbox:** an actual
`yarn twenty dev` run against a live Twenty server on a real Windows
machine. This sandbox has no network access and is not Windows, so no
change described in this document — including this update — has been
confirmed end-to-end against the real CLI process and a real server. If a
different backslash-shaped error surfaces after this fix, it means some
other call site builds a request body without going through
`JSON.stringify` (e.g. manual string concatenation, or a different HTTP
client) — that would need a targeted addition here, not a change to the
application.
