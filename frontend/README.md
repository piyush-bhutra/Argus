# Debate Insight Dashboard

Build a frontend dashboard for a debate-based fact-verification tool as a

new project. This is a standalone academic demo — no login/auth needed,

single user.

The frontend talks to a separate FastAPI backend. Use an environment

variable for the base URL (e.g. VITE_API_BASE_URL or similar, whatever's

idiomatic for the stack you generate), defaulting to http://localhost:8000

for local development. Don't hardcode the URL anywhere.

PAGES/VIEWS:

1. Claim input screen

   - Text input for a claim, "Start Debate" button

   - POST to /debate/start with { "claim": string, "rounds": 3 }

   - Response gives { "debate_id": string } — navigate to the debate view

2. Debate view (main screen)

   - Fetch GET /debate/{debate_id}/transcript

   - Response: { "arguments": Argument[], "status": "in_progress" | "complete" }

   - Argument shape: { id, agent: "advocate"|"skeptic", round, text, attacks: string[], self_confidence: number }

   - Render as a two-column or chat-style alternating transcript — advocate

     on one side, skeptic on the other, grouped by round, each argument

     showing its confidence as a small badge

   - If status is "in_progress", show a subtle loading/live indicator, with

     polling to refresh

3. Argument graph visualization

   - Fetch GET /debate/{debate_id}/graph → { "nodes": [...], "edges": [...] }

   - Render as a simple force-directed or node-link graph (attacks as

     directed edges between argument nodes) — clean and readable over fancy

   - Nodes belonging to advocate vs skeptic should be visually distinct

     (color or shape)

4. Verdict panel

   - Fetch GET /debate/{debate_id}/verdict

   - Response: { claim, raw_probability, calibrated_probability,

     grounded_extension: { advocate: string[], skeptic: string[] },

     explanation: string }

   - Show calibrated_probability prominently (gauge or large percentage),

     raw_probability as a smaller secondary figure, explanation text below

   - Highlight which arguments survived (from grounded_extension) directly

     in the transcript view — e.g. a "survived" badge on those specific

     argument cards

DESIGN:

- Clean, modern, dark-mode-friendly dashboard aesthetic — this is a

  technical/analytical tool, not a consumer app, so favor clarity and data

  density over decoration

- Responsive, but desktop-first is fine — this will be demoed on a laptop

Use realistic mock data matching the shapes above for all four views so

the UI is fully navigable and demoable before the real backend is wired in.

IMPORTANT: frontend only. No backend logic, no real API calls beyond the

fetch calls described above — this connects to a separately-built FastAPI

service, not something you should generate.

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/765ba527-837a-4cfd-8eec-2698813dc19b).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
