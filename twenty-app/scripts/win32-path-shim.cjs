"use strict";

/**
 * win32-path-shim.cjs
 * -----------------------------------------------------------------------
 * Root cause of the "Resource path must not contain backslashes" /
 * "filePath contains unsafe characters or path traversal" errors:
 *
 *   The Twenty CLI (twenty-sdk@2.27.0) builds every manifest field it
 *   uploads to the server — sourceHandlerPath, builtHandlerPath,
 *   sourceComponentPath, builtComponentPath, and the checksum/upload
 *   filePath — with Node's built-in `path.relative()` / `path.join()` /
 *   `path.resolve()`. On win32, those functions return backslash-
 *   separated strings by design (that's the whole point of `path` vs.
 *   `path.posix`). The CLI never normalizes its own output to POSIX
 *   before treating it as a portable resource identifier, so the
 *   backslashes go straight into the manifest and the upload payload,
 *   where the Twenty server's path-safety validators reject them.
 *
 *   This is a bug in the CLI (twenty-sdk), not in this application:
 *   `src/` never builds a resource path itself (see WINDOWS_PATH_FIX.md
 *   for the full audit) — every rejected field is CLI-generated.
 *
 * Fix strategy:
 *   Node's `require("path")` returns one singleton module object shared
 *   by every module in the process, including everything inside the
 *   CLI's dependency graph. Wrapping `path.join` / `path.resolve` /
 *   `path.relative` once, here, before the CLI ever runs, normalizes
 *   every path the CLI computes to forward slashes — without touching
 *   node_modules, without patching the CLI's minified bundle byte-for-
 *   byte, and without depending on any twenty-sdk internal variable
 *   names or file layout that could shift between patch releases.
 *
 *   Forward slashes are safe to use in ordinary (non-UNC, non-\\?\)
 *   Windows paths — the Win32 API and Node's fs layer both accept them
 *   interchangeably with backslashes — so this only changes what gets
 *   sent to the server; it doesn't change how files are read from disk.
 *
 * Scope / safety:
 *   - No-ops entirely on any platform other than win32.
 *   - Wrapped functions still return their real result for every path
 *     that already comes back POSIX-flavored; the wrapper is a pure
 *     string post-process (split/join) and can't change *which* file a
 *     path points to on disk, only its separator characters.
 *   - Wrapped in try/catch so a failure here can never block the CLI
 *     from running (worst case: this shim becomes a no-op and the
 *     original backslash bug resurfaces, which is the pre-existing
 *     behavior anyway).
 */
try {
  if (process.platform === "win32") {
    const path = require("path");

    const toPosix = (value) =>
      typeof value === "string" ? value.split("\\").join("/") : value;

    const wrap = (fn) =>
      function patched(...args) {
        return toPosix(fn.apply(path, args));
      };

    path.join = wrap(path.join);
    path.resolve = wrap(path.resolve);
    path.relative = wrap(path.relative);
  }
} catch (shimError) {
  // Never let the shim itself break the CLI: fall through silently.
  // (Visible only with DEBUG=twenty:win32-shim, to avoid noise for the
  // overwhelming majority of contributors who aren't on Windows.)
  if (process.env.DEBUG && process.env.DEBUG.includes("twenty:win32-shim")) {
    console.warn("[win32-path-shim] failed to install:", shimError);
  }
}
