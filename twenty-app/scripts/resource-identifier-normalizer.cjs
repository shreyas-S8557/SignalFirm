"use strict";

/**
 * resource-identifier-normalizer.cjs
 * -----------------------------------------------------------------------
 * v4. Supersedes both win32-path-shim.cjs (v1/v2, globally overrode
 * `path.*` — broke native modules like `sharp`) and the v3 revision of
 * this same file (hooked `fs.writeFileSync` / `fs.promises.writeFile` for
 * `manifest.json`, plus `fetch`/`axios` request-body interceptors).
 *
 * WHY v3 DID NOT ACTUALLY FIX THE REPORTED BUG
 * -----------------------------------------------------------------------
 * This was checked directly against the real, installed
 * `twenty-sdk@2.27.0` package (`node_modules/twenty-sdk/dist/*.mjs`), not
 * assumed. Findings:
 *
 * 1. `sourceHandlerPath` / `builtHandlerPath` (logic functions) and
 *    `sourceComponentPath` / `builtComponentPath` (front components) are
 *    both built the same way, from the manifest-building pass over
 *    `**\/*.ts(x)`:
 *
 *        import { relative as f } from "path";
 *        ...
 *        let s = f(appPath, fileAbsolutePath);           // path.relative()
 *        sourceHandlerPath: s,
 *        builtHandlerPath: s.replace(/\.tsx?$/, ".mjs"),
 *
 *    `path.relative()` is OS-native and returns backslash-separated
 *    segments on win32 — confirming the original root-cause analysis.
 *
 * 2. `manifest.json` is written with:
 *
 *        await x(manifestPath, JSON.stringify(manifest, null, 2) + "\n");
 *
 *    so hooking `fs.writeFileSync`/`fs.promises.writeFile` on the
 *    filename **did** cover this path. This part of v3 was correct.
 *
 * 3. But the *upload* call — the one actually producing the
 *    "Failed to upload ... filePath contains unsafe characters" /
 *    `INVALID_LOGIC_FUNCTION_INPUT` / `INVALID_FRONT_COMPONENT_INPUT`
 *    errors quoted in the bug report — does NOT send a plain JSON body.
 *    `uploadFile()` sends a GraphQL multipart upload:
 *
 *        let u = JSON.stringify({ query: "...UploadApplicationFile...",
 *          variables: { file: null, applicationUniversalIdentifier: r,
 *                       filePath: t, fileFolder: l } });
 *        let f = new FormData();
 *        f.append("operations", u);       // <- filePath is IN HERE
 *        f.append("map", JSON.stringify({ 0: ["variables.file"] }));
 *        f.append("0", new Blob([...]), a);
 *        await this.client.post("/metadata", f);
 *
 *    `config.data` on that axios request is a `FormData` instance, not a
 *    plain object or a JSON string. v3's axios/fetch interceptors did
 *    `typeof config.data === "object"` (true for FormData) and then
 *    `Object.keys(config.data)` to look for a `filePath` key —  but
 *    `FormData` doesn't expose appended fields as enumerable own
 *    properties, so that scan always found nothing and silently passed
 *    the unmodified, backslash-containing `operations` field straight
 *    through. This is the actual, confirmed reason the error in the bug
 *    report survived the v3 fix.
 *
 * THE ACTUAL FIX: patch `JSON.stringify` itself
 * -----------------------------------------------------------------------
 * Both code paths above — the manifest write AND the upload's
 * `operations` field — construct their string via a literal
 * `JSON.stringify(...)` call before anything is written to disk or sent
 * over the wire. That's the one true, common serialization boundary: it
 * doesn't matter afterwards whether the resulting string goes into
 * `fs.writeFile`, a `FormData` field, a raw `fetch` body, or an axios
 * JSON body — by the time any of those run, the backslashes are already
 * gone, because `JSON.stringify` never produced them.
 *
 * `JSON.stringify` is patched (win32 only) to, for object/array input:
 *   1. Walk a **non-mutating structural clone** of the value — never the
 *      original object — replacing `\` -> `/` only on string values
 *      whose *key* is in KNOWN_RESOURCE_PATH_KEYS (see below).
 *   2. Only recurse into plain objects/arrays; anything else (Date,
 *      Buffer, class instances, Blob, FormData, Map, etc.) is returned
 *      as-is, untouched, exactly as `JSON.stringify` would have received
 *      it — so this cannot change how those types serialize (e.g.
 *      `toJSON()` methods still run normally, just on the same
 *      instance).
 *   3. Call the *original* `JSON.stringify` on the clone with the same
 *      `replacer`/`space` arguments the caller passed.
 *
 * Cloning instead of mutating in place matters because the CLI's own
 * variable `t` (`builtHandlerPath`) — the exact string that becomes
 * `sourceHandlerPath`/`builtHandlerPath` in the manifest — is a plain
 * relative string, never reused afterwards as a filesystem path (the
 * actual on-disk read in `uploadFile()` uses a separate `filePath`
 * argument resolved with `path.resolve()`, not this field). But cloning
 * rather than mutating is the safer default regardless: it guarantees
 * this fix can only ever change what gets serialized to JSON, never any
 * value the CLI (or a dependency) still holds a live reference to and
 * might later pass to a real, native filesystem call.
 *
 * The `fs.writeFileSync`/`fs.promises.writeFile` hook from v3 is kept as
 * a second, redundant safety net specifically for `manifest.json` (in
 * case of a future SDK release that builds that file's bytes without
 * going through `JSON.stringify`) — but it is no longer load-bearing;
 * the `JSON.stringify` patch alone fixes both the manifest and the
 * upload path. The v3 fetch/axios request-body interceptors have been
 * removed: they never actually matched the FormData upload calls that
 * produce this bug (see point 3 above), and keeping non-functional hooks
 * around is worse than removing them — they gave the false impression
 * this class of bug was covered.
 *
 * Scope / safety (unchanged from v3's design goals):
 *   - No-ops entirely on any platform other than win32.
 *   - Only rewrites string values under a fixed allow-list of known
 *     resource-identifier key names — not every string `JSON.stringify`
 *     ever sees.
 *   - Every hook is wrapped in try/catch and falls back to the original,
 *     unmodified function on any error, so a bug in this file can never
 *     block the CLI from running.
 *   - Does not touch `path.join`/`path.resolve`/`path.relative` at all,
 *     so native modules (`sharp`, etc.) that depend on real, native
 *     win32 paths from those functions are unaffected.
 */

const KNOWN_RESOURCE_PATH_KEYS = new Set([
  "resourcePath",
  "sourceHandlerPath",
  "builtHandlerPath",
  "sourceComponentPath",
  "builtComponentPath",
  "filePath",
  "path",
]);

function toPosix(value) {
  return typeof value === "string" ? value.split("\\").join("/") : value;
}

/**
 * Non-mutating structural clone: rewrites backslashes only on string
 * values whose key is in KNOWN_RESOURCE_PATH_KEYS. Any object that isn't
 * a plain object or array (Date, Buffer, Blob, FormData, class instances,
 * Map, Set, etc.) is returned by reference, completely untouched, so its
 * normal serialization behavior (including any custom `toJSON()`) is
 * unaffected.
 */
function cloneAndNormalize(value, seen) {
  if (value === null || typeof value !== "object") {
    return value;
  }

  if (seen.has(value)) {
    // Circular reference: hand back the original reference. JSON.stringify
    // will throw on it exactly as it would have without this patch.
    return value;
  }

  if (Array.isArray(value)) {
    seen.add(value);
    return value.map((item) => cloneAndNormalize(item, seen));
  }

  const proto = Object.getPrototypeOf(value);
  const isPlainObject = proto === Object.prototype || proto === null;
  if (!isPlainObject) {
    return value;
  }

  seen.add(value);
  const out = {};
  for (const key of Object.keys(value)) {
    const v = value[key];
    if (KNOWN_RESOURCE_PATH_KEYS.has(key) && typeof v === "string") {
      out[key] = toPosix(v);
    } else {
      out[key] = cloneAndNormalize(v, seen);
    }
  }
  return out;
}

function installJsonStringifyHook() {
  const originalStringify = JSON.stringify;

  JSON.stringify = function patchedStringify(value, replacer, space) {
    if (value !== null && typeof value === "object") {
      try {
        const cloned = cloneAndNormalize(value, new Set());
        return originalStringify.call(JSON, cloned, replacer, space);
      } catch {
        // Fall through to the original, unmodified call below.
      }
    }
    return originalStringify.call(JSON, value, replacer, space);
  };
}

/**
 * Redundant safety net for manifest.json specifically (see header comment
 * — not required for the fix to work, kept for defense in depth).
 */
function installManifestWriteHook(fs) {
  const path = require("path");

  const wrapWriter = (original) =>
    function patchedWriter(file, data, ...rest) {
      try {
        const fileName =
          typeof file === "string" ? path.basename(file) : undefined;
        if (fileName === "manifest.json" && typeof data === "string") {
          const parsed = JSON.parse(data);
          const normalized = cloneAndNormalize(parsed, new Set());
          // Use the ALREADY-PATCHED JSON.stringify for consistent output,
          // but this call is idempotent even if that patch is somehow
          // absent (the value is already normalized by cloneAndNormalize).
          const rewritten = JSON.stringify(normalized, null, 2);
          return original.call(fs, file, rewritten, ...rest);
        }
      } catch {
        // Fall through to the original, unmodified call below.
      }
      return original.call(fs, file, data, ...rest);
    };

  if (typeof fs.writeFileSync === "function") {
    fs.writeFileSync = wrapWriter(fs.writeFileSync);
  }
  if (fs.promises && typeof fs.promises.writeFile === "function") {
    const originalAsync = fs.promises.writeFile;
    fs.promises.writeFile = async function patchedWriteFileAsync(
      file,
      data,
      ...rest
    ) {
      try {
        const path2 = require("path");
        const fileName =
          typeof file === "string" ? path2.basename(file) : undefined;
        if (fileName === "manifest.json" && typeof data === "string") {
          const parsed = JSON.parse(data);
          const normalized = cloneAndNormalize(parsed, new Set());
          const rewritten = JSON.stringify(normalized, null, 2);
          return await originalAsync.call(fs.promises, file, rewritten, ...rest);
        }
      } catch {
        // Fall through to the original, unmodified call below.
      }
      return await originalAsync.call(fs.promises, file, data, ...rest);
    };
  }
}

try {
  if (process.platform === "win32") {
    installJsonStringifyHook();
    installManifestWriteHook(require("fs"));
  }
} catch (installError) {
  // Never let this file be the reason the CLI fails to start.
  if (
    process.env.DEBUG &&
    process.env.DEBUG.includes("twenty:resource-path-normalizer")
  ) {
    console.warn(
      "[resource-identifier-normalizer] failed to install:",
      installError,
    );
  }
}

module.exports = { cloneAndNormalize, KNOWN_RESOURCE_PATH_KEYS };
