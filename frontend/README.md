# Argus — Frontend

React dashboard for the Argus debate-based fact-verification system. Renders the live debate
transcript, the argument attack graph, and the calibrated verdict.

Stack: React 19 + TanStack Start (SSR) + TanStack Router + TanStack Query + Tailwind CSS v4 +
Vite.

## Development

Needs Node.js 20+ and the FastAPI backend running (see the repo root README).

```sh
npm install
npm run dev
```

The dev server prints a `http://localhost:<port>` URL. It talks to the backend at
`http://localhost:8000` by default — override with `VITE_API_BASE_URL`.

```sh
npm run build     # production build (nitro / Cloudflare target)
npm run lint      # eslint
npx tsc --noEmit  # typecheck
```

## Layout

- `src/routes/` — file-based routes: `index.tsx` (claim entry), `debate.$debateId.tsx`
  (transcript / graph / verdict tabs), `__root.tsx` (shell + error boundaries).
- `src/components/debate/` — `TranscriptView`, `ArgumentGraph` (hand-rolled force-directed
  SVG), `VerdictPanel`.
- `src/lib/` — `api.ts` (backend calls + mock fallback), `types.ts`, `mock-data.ts`.
- `src/styles.css` — Tailwind v4 theme tokens (dark, oklch).
