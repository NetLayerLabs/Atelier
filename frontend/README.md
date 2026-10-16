# Atelier — Creative Director Dashboard (frontend)

Next.js 16 (App Router) · TailwindCSS 4 · Framer Motion · zustand.

```bash
pnpm install
cp .env.example .env.local   # NEXT_PUBLIC_API_BASE defaults to http://localhost:8787
pnpm dev                     # http://localhost:3100
```

- `src/lib/types.ts` / `src/lib/api.ts` — typed client mirroring `../CONTRACT.md`.
- `/workspace` (`src/components/workspace/`, `src/lib/workspace.ts`) — v5 Brand workspace: onboarding for the
  brand's profile, brand book, suppliers, price list, guardrails and sales history (CSV/XLSX import with preview +
  validation). The studio's approve button is disabled until the workspace is ready (`WorkspaceGate`).
- `src/lib/store.ts` — flow state (analyse → generate → refine → approve → poll run every 800ms).
- There is no mock / fixture mode: every screen talks to the real backend. A service that is not connected shows
  an error state with its setup hint and a Retry button.
- The backend must allow the frontend origin in `CORS_ORIGINS` (default `http://localhost:3100`).
