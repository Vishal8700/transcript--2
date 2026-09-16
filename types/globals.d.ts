/**
 * Makes the `chrome` extension API available as a global in all JS files
 * without needing per-file reference directives.
 * Relies on @types/chrome being installed (node_modules/@types/chrome).
 */

// This empty export makes the file a module, allowing the global augmentation below.
export {}

declare global {
  const chrome: typeof import("chrome")
}
