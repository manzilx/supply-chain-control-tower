---
name: Do not run `next build` to verify against a project with a live `npm run dev`
description: Running `next build` in the user's Next.js app corrupts the dev server's .next cache and breaks their page with module-not-found errors
type: feedback
originSessionId: a40f33a9-c482-4542-bc2d-1d7d2e106a3b
---
When verifying a Next.js change, do NOT run `npx next build` / `npm run build` in the user's project directory. It overwrites the shared `.next/` with production chunks that `next dev` cannot resolve, and the user sees `Error: Cannot find module './NNN.js'` on every page load. Happened twice on this project (after M1 and after M3).

**Why:** Next.js dev and production share the same `.next` output directory. Production build artifacts don't work under `next dev`, and vice versa. The user usually has `npm run dev` running continuously.

**How to apply:**
- Trust `tsc --noEmit` or the TypeScript language server for type-check verification instead — run `npx tsc --noEmit` if a check is really needed.
- Or do a dry compile in a throwaway dir with `next build --no-lint` and a custom output — but simpler to just skip the build step.
- If a full build verification is genuinely required, ask the user to stop `npm run dev` first, then `rm -rf .next` and restart after.
- After accidentally running `next build`, tell the user to `rm -rf .next` and restart the dev server.
