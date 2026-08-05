#!/usr/bin/env node
"use strict";

/**
 * twenty-cli.cjs
 * -----------------------------------------------------------------------
 * Cross-platform entry point used by the "twenty" npm script instead of
 * calling the `twenty` binary directly.
 *
 * Preload target update: this wrapper now preloads
 * `resource-identifier-normalizer.cjs`, not `win32-path-shim.cjs`. The old
 * shim globally overrode `path.join`/`path.resolve`/`path.relative` for
 * the whole process, which also broke native modules (e.g. `sharp`) that
 * legitimately call `path.resolve()` to locate their own binaries. The
 * replacement never touches `path.*`; it normalizes only the known
 * resource-identifier fields (`sourceHandlerPath`, `builtHandlerPath`,
 * `sourceComponentPath`, `builtComponentPath`, `filePath`, manifest/
 * checksum `path` entries) at the point they're written to
 * `manifest.json` or sent in an upload/metadata request body. See that
 * file's header comment for the full design. The history below (v2/v3,
 * NODE_OPTIONS) is about how the CLI subprocess itself is launched and
 * still applies unchanged.
 *
 * v3 of this wrapper: does NOT use NODE_OPTIONS.
 * -----------------------------------------------------------------------
 * v2 preloaded the win32 path shim by setting:
 *
 *     NODE_OPTIONS = --require "D:\...\win32-path-shim.cjs"
 *
 * and letting that string flow through the environment to whatever Node
 * process eventually ran the CLI. On Windows that failed:
 *
 *     Cannot find module
 *     D:SignalFirm_CRMSignalFirm_CRMtwenty-appscriptswin32-path-shim.cjs
 *
 * every backslash gone. WHY: NODE_OPTIONS isn't just an opaque string
 * Node hands to the OS — Node parses it itself with a small
 * shell-flavored tokenizer, and in that tokenizer a backslash is an
 * *escape character*. `\S`, `\S`, `\t`, `\w`, `\s`, `\c` inside the
 * quoted path each got consumed as an escape sequence instead of a
 * literal backslash, which is exactly "every backslash stripped" — not
 * cmd.exe mangling the value in transit, but Node's own NODE_OPTIONS
 * parser doing it on the way in. Quoting the path didn't help, because
 * quoting only protects against *shell* tokenization (spaces); it does
 * nothing about NODE_OPTIONS' own escape-character handling. There is no
 * quoting strategy that fixes this — the mechanism itself is the wrong
 * tool for passing a literal Windows path, so this version stops using
 * it entirely.
 *
 * NEW APPROACH: invoke Node directly, with `--require` as a real argv
 * element.
 * -----------------------------------------------------------------------
 *   `child_process.spawnSync(cmd, argsArray, { shell: false })` (the
 *   default — no shell option is set below) never builds a single
 *   command-line *string* that anything re-parses. Each element of
 *   `argsArray` is delivered to the child process as its own discrete
 *   argument — on Windows, via Node's own correct low-level argument
 *   encoding for `CreateProcess`, not via `cmd.exe`; on POSIX, via
 *   `execve`'s native `argv[]`. Neither path involves a tokenizer that
 *   treats backslash as an escape character or requires quoting spaces,
 *   because there is no intermediate string to tokenize at all.
 *
 *   Concretely, this wrapper now runs:
 *
 *       <node binary> --require <shim.cjs> <cli-entry.js> <...argv>
 *
 *   with `--require`, the shim path, the CLI's real entry `.js` file,
 *   and the forwarded `argv` all passed as separate array elements —
 *   exactly the "invoke Node directly, preload with --require, pass the
 *   CLI JS entry as the script, forward argv normally" shape.
 *
 * Finding the CLI's real entry `.js` file without `require`-ing
 * twenty-sdk/package.json
 * -----------------------------------------------------------------------
 *   Passing the *actual* entry file to `node` (rather than the
 *   node_modules/.bin/twenty shim) means this wrapper does need to know
 *   where that file lives — twenty-sdk's `"bin"` field is the only
 *   authoritative source for that. `require("twenty-sdk/package.json")`
 *   is still off the table (see the previous round: `"exports"`
 *   encapsulation makes that throw `ERR_PACKAGE_PATH_NOT_EXPORTED`, by
 *   design, on modern Node).
 *
 *   The distinction that matters: `"exports"` encapsulation is a
 *   restriction Node's *module resolver* enforces on `require()` / static
 *   `import` — it has no bearing on plain filesystem access. Reading
 *   `twenty-sdk/package.json` with `fs.readFileSync()` opens the exact
 *   same bytes on disk, but never goes anywhere near the part of Node
 *   that checks `"exports"`, so `ERR_PACKAGE_PATH_NOT_EXPORTED` simply
 *   doesn't apply. This isn't a loophole in the encapsulation — package
 *   managers themselves resolve every dependency's `"bin"` field by
 *   reading `package.json` from disk (that's how `node_modules/.bin`
 *   gets populated in the first place); this wrapper is doing the same
 *   well-established thing they do, using the same public, documented
 *   field, not reaching for anything internal to the package's code.
 *   `require()` is what's avoided here, not "ever looking at the file".
 */

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const projectRoot = path.join(__dirname, "..");
const sdkDir = path.join(projectRoot, "node_modules", "twenty-sdk");
const sdkPkgJsonPath = path.join(sdkDir, "package.json");

function resolveCliEntry() {
  if (!fs.existsSync(sdkPkgJsonPath)) {
    throw new Error(
      `Could not find ${sdkPkgJsonPath}. Run "yarn install" first.`,
    );
  }

  // Plain fs read + JSON.parse — not `require()` — so this is unaffected
  // by twenty-sdk's "exports" field. See the comment block above.
  const pkg = JSON.parse(fs.readFileSync(sdkPkgJsonPath, "utf8"));

  let binRelPath;
  if (typeof pkg.bin === "string") {
    binRelPath = pkg.bin;
  } else if (pkg.bin && typeof pkg.bin === "object") {
    binRelPath = pkg.bin.twenty ?? Object.values(pkg.bin)[0];
  }

  if (!binRelPath) {
    throw new Error(
      `twenty-sdk's package.json has no usable "bin" entry (checked ${sdkPkgJsonPath}).`,
    );
  }

  // path.join normalizes "./dist/cli.cjs"-style values from package.json
  // and works the same whether the declared separator was "/" or the
  // platform's own — we're building a real filesystem path here, not a
  // module specifier, so there is no exports/module-resolution step for
  // this to trip over.
  const entryPath = path.join(sdkDir, binRelPath);

  if (!fs.existsSync(entryPath)) {
    throw new Error(
      `twenty-sdk's package.json declares bin "${binRelPath}", but ${entryPath} does not exist.`,
    );
  }

  return entryPath;
}

const shimPath = path.join(__dirname, "resource-identifier-normalizer.cjs");
const cliEntry = resolveCliEntry();

// No shell (the default), no NODE_OPTIONS, no string concatenation of
// any path: every path below is its own argv element, verbatim, exactly
// as spaces and backslashes appear on disk.
const result = spawnSync(
  process.execPath, // reuse whichever Node binary is already running this wrapper
  ["--require", shimPath, cliEntry, ...process.argv.slice(2)],
  { stdio: "inherit" },
);

if (result.error) {
  console.error(result.error);
  process.exit(1);
}

process.exit(result.status === null ? 1 : result.status);
