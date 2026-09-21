> ## ARCHIVED — describes a superseded architecture
>
> Written **2026-08-30**, before the evidence-grounded redesign of 2026-09-20.
> Kept as a historical record of the Review-1 system. **Do not use it to
> understand how Argus works today.**
>
> Specifically out of date: it describes an **LLM fact-check pass** (replaced by
> retrieval plus a symbolic reasoner), a single `attacks_argument_id` per
> argument (now an `attacks` list with free targeting), and lists the FEVER
> dataset and evaluation as "not done" (both complete).
>
> Current documents: [`docs/RESULTS.md`](../RESULTS.md) ·
> [`docs/PLAN.md`](../PLAN.md) · [`PROJECT_STATE.md`](../../PROJECT_STATE.md) §4a ·
> `debate_system_prd.md` Appendix A

# Argus — Project Snapshot

**Generated:** 2026-08-30, from direct inspection of the codebase (not from prior docs).
**Repo:** `C:\AI-Project` · GitHub `piyush-bhutra/Argus` · branch `master`
**What it is:** A multi-agent debate system for fact verification. Two LLM agents (Advocate,
Skeptic) argue a factual claim across structured rounds. Their arguments form an attack
graph; a formal argumentation engine (Dung's grounded extension) decides which arguments
survive; an LLM fact-check pass and a Bayesian judge combine that structural signal with
evidence and each agent's self-reported confidence into a calibrated **P(claim is true)**,
with the full transcript, graph, and reasoning exposed. Course project for BITE308L/BITE308P
(AI theory + lab).

**Stack in one line:** Python 3.11 + FastAPI backend (in-memory state, background tasks) ·
Google Gemini as the LLM (OpenAI-SDK-compatible endpoint) · React 19 + TanStack Start (SSR)
+ Tailwind v4 frontend, polling the backend.

**Status:** End-to-end working. A real claim → live streamed debate → attack graph →
grounded extension → calibrated verdict, all rendered in the browser. Verified live this
session. Not done: FEVER dataset, trained calibrator, ECE evaluation (all deliberately
deferred — see §4).

---

## 1. Backend — Current State

### 1.1 File inventory (`app/`)

| File | What it does | Status |
|---|---|---|
| `app/main.py` | FastAPI app factory. Registers CORS (`allow_origins=["*"]`), includes the router, and a `lifespan` handler that calls `debate_store.load_demos()` on startup. `GET /` returns a welcome JSON. | Working |
| `app/api/routes.py` | The 4 debate endpoints (§1.2). All read/write the in-memory `debate_store`; `/debate/start` schedules `run_pipeline` as a FastAPI `BackgroundTask`. | Working |
| `app/core/config.py` | Pydantic-settings `Settings` loaded from `.env`: `llm_api_key`, `llm_model`, `llm_base_url` (default `https://api.cerebras.ai/v1`), `log_dir`. Singleton `settings`. | Working |
| `app/core/logger.py` | `setup_logging()` — INFO level, writes `logs/app.log` + stdout. Exports `logger` (name `"argus"`). | Working |
| `app/models/schemas.py` | All Pydantic models (§3). | Working |
| `app/services/orchestrator.py` | Runs the debate loop: N rounds, alternating advocate→skeptic turns, each turn one LLM call with 3 parse-retry attempts, markdown-fence stripping, `concede` handling, early-termination guard (fixed bug — never ends round 1 before both sides speak; from round 2 ends only on mutual concession). Optional `on_argument(transcript)` callback fired after each argument for live streaming. | **Working** |
| `app/services/grok_client.py` | LLM wrapper. `call_grok(user_prompt, system_prompt) -> str` via the `openai` SDK pointed at `settings.llm_base_url`. Lazy client init (validates key at first call, not import). SDK internal retries disabled; our loop = 2 short retries on transient 429; **daily-quota 429s (`PerDayPerProject`) fail fast**. Function name is historical (was xAI Grok). | **Working** |
| `app/services/semantics_engine.py` | Dung's Abstract Argumentation Framework grounded extension via `networkx` + a fixpoint IN/OUT/UNDEC labeller (§1.3). Returns `{"advocate": [...ids], "skeptic": [...ids]}` of surviving arguments. | **Working, well-tested** |
| `app/services/judge.py` | Bayesian judge (§1.3): `compute_raw_probability(grounded, fact_results, arguments) -> float` — sigmoid over weighted advocate-minus-skeptic margins. `fit_calibrator` / `apply_calibration` — sklearn `IsotonicRegression`. | **Working** (calibrator never trained — see §4) |
| `app/services/fact_checker.py` | `check_transcript(claim, arguments) -> list[FactCheckResult]` — ONE batched LLM call scoring every argument's core assertion in `[-1, 1]`. Neutral (`0.0`) fallback for every argument on any parse/API failure. Thin `check_argument(text)` wrapper kept. | **Working** (LLM opinion, not retrieval — see §4) |
| `app/services/debate_store.py` | In-memory `dict[str, DebateRecord]`. `create`, `get`, `set_transcript` (stores a copy — orchestrator streams into it), `set_result`, `set_error`, `load_demos()` (seeds `data/demo_debates.json` at startup). No DB; state lost on restart except demos. | Working (MVP scope) |
| `app/services/pipeline.py` | Glue. `run_pipeline(debate_id)`: `run_debate(...)` (streaming into the store) → `compute_grounded_extension` → `check_transcript` → `compute_raw_probability` → optional `apply_calibration` (loads `data/calibrator.pkl` if present, else calibrated = raw) → builds `Verdict` + templated `explanation` string + `GraphResponse` → `set_result`. Catches everything → `set_error` with a friendly message. Also `assemble_verdict()` and `build_graph()` as reusable pieces. | Working |

**No `__init__.py` files anywhere in `app/`** — it works via namespace packages + `pytest.ini`'s `pythonpath = .`. `uvicorn app.main:app` and `python -m pytest` both work; bare `pytest` may not resolve imports.

### 1.2 API endpoints

Base URL in dev: `http://localhost:8000`. CORS wide open. No auth. State is per-process in memory.

| Method | Path | Request | Response | Notes |
|---|---|---|---|---|
| `POST` | `/debate/start` | `{ "claim": string, "rounds"?: int }` (`StartDebateRequest`, `rounds` default 3, clamped to `[1,5]`) | `{ "debate_id": string }` (`StartDebateResponse`). id shape `debate-<12 hex>` | Empty/whitespace claim → `422`. Returns immediately; `run_pipeline` runs in the background. Frontend always sends `rounds: 2`. |
| `GET` | `/debate/{id}/transcript` | — | `{ "arguments": Argument[], "status": "in_progress" \| "complete", "rounds": int }` (`TranscriptResponse`) | Unknown id → `404`. Pipeline errored → `500` with `detail` = friendly error string. `arguments` grows over successive polls while the debate streams. |
| `GET` | `/debate/{id}/verdict` | — | `Verdict` (§3) | `404` unknown · `500` errored · `409` "verdict not ready yet" (debate still running). |
| `GET` | `/debate/{id}/graph` | — | `{ "nodes": GraphNode[], "edges": GraphEdge[] }` (`GraphResponse`) | `404` unknown. Returns the stored graph once complete, else builds one on the fly from the partial transcript (so the graph grows live too). Does **not** 500 on pipeline error — returns whatever partial graph exists. |
| `GET` | `/` | — | `{ "message": "Welcome to the Argus API" }` | Health check. |

**Trigger chain:** `POST /debate/start` → `debate_store.create()` → `BackgroundTasks.add_task(run_pipeline, id)` → `run_debate()` calls Gemini once per turn, each turn calls `on_argument` → `set_transcript()` (visible on next `/transcript` poll) → after all turns: one fact-check LLM call → judge math → `set_result()` (status flips to `complete`, `/verdict` and `/graph` now return full data).

### 1.3 Algorithms

**Grounded extension (Dung's AF)** — `semantics_engine.py`, **fully working, 3 unit tests.**
Build a directed graph: nodes = arguments, edge A→B = "A attacks B". Label every node `UNDEC`.
Iterate to a fixpoint: a node becomes `IN` when *every* attacker is `OUT` (so an unattacked
node is immediately `IN`); a node becomes `OUT` when *any* attacker is `IN`. Stop when a full
pass changes nothing. Nodes still `UNDEC` sit in unbroken attack cycles. Return the `IN`
nodes, split by which agent authored them. This is the "which arguments actually survive
scrutiny" signal, independent of how confident either agent sounded.

**Bayesian judge** — `judge.py`, **fully working, 3 unit tests.**
`raw_P = sigmoid( 1.0·Δstructural + 1.0·Δfactcheck + 0.5·Δconfidence )` where each Δ is
advocate-value minus skeptic-value:
- `Δstructural` = (# advocate arguments surviving the grounded extension) − (# skeptic surviving)
- `Δfactcheck` = mean fact-check support of advocate arguments − mean of skeptic arguments
- `Δconfidence` = mean self-reported confidence of advocate arguments − mean of skeptic
Zero signal → `sigmoid(0)` = 0.5. Weights are module constants (`STRUCTURAL_WEIGHT=1.0`,
`FACTCHECK_WEIGHT=1.0`, `CONFIDENCE_WEIGHT=0.5`).

**Isotonic calibration** — `judge.py`, **math works & tested, but never trained.**
`fit_calibrator(raw_probs, bool_labels)` fits sklearn `IsotonicRegression(out_of_bounds="clip")`;
`apply_calibration` maps a raw P through it. `pipeline.py` loads `data/calibrator.pkl` if it
exists — it doesn't, so **`calibrated_probability` always equals `raw_probability`** today, and
the verdict explanation says so explicitly.

**Debate orchestration** — `orchestrator.py`, **working, 6 unit tests.**
For each round, for each agent: build a system prompt (role) + user prompt (claim + full
transcript so far + the required JSON shape). Call the LLM. Strip ```` ```json ```` fences,
`json.loads`. If `concede: true` → mark conceded. Else extract `argument_text`,
`attacks_argument_id` (→ `attacks` list), `confidence` (coerced to float, clamped `[0,1]`),
append an `Argument` with id `arg_<n>`, fire `on_argument`. Up to 3 parse attempts per turn
(with an escalating "return ONLY JSON" nudge); 3 failures = treated as a concession.
Early-termination guard: never end in round 1 before the opponent has spoken; from round 2
on, end only if both agents conceded in the same round.

**LLM fact-check** — `fact_checker.py`, **working, 4 unit tests (mocked).**
One prompt lists the claim + every argument's text; asks for JSON `{results: [{argument_id,
support_score ∈ [-1,1], reasoning}]}`. Parsed defensively; any argument missing from the
response, or any failure at all, yields a neutral `0.0`. `evidence_sentences` currently holds
the one-line `reasoning` string (or is empty) — there is no evidence corpus.

### 1.4 Environment variables (backend)

Loaded from `.env` at repo root (gitignored). `.env.example` is committed.

| Var | Purpose | Example |
|---|---|---|
| `LLM_API_KEY` | API key for the LLM provider | *(Gemini key)* |
| `LLM_MODEL` | Model id | `gemini-3.5-flash-lite` |
| `LLM_BASE_URL` | OpenAI-SDK-compatible endpoint | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `LOG_DIR` | Where `app.log` is written | `./logs` |

Provider is fully swappable via these three vars. Cerebras (`gpt-oss-120b`,
`https://api.cerebras.ai/v1`) also works — kept commented in `.env.example`.
**Model-id note:** the newest Gemini flash models have a ~20 requests/**day** free cap
(`gemini-3.6-flash`); `gemini-2.0-flash` and `gemini-2.5-flash-lite` return 404. Quota is
per-model, so a `*-flash-lite` id gives headroom. A live 2-round debate ≈ 5 LLM calls.

### 1.5 Test suite

`python -m pytest` → **32 passed, 0 skipped** (~5 s). All LLM calls are mocked; no network.

| File | Count | Covers |
|---|---|---|
| `test_app.py` (repo root) | 3 | End-to-end API flow via `TestClient` (mocked pipeline): start → transcript → graph → verdict; 404s; empty-claim 422 |
| `tests/test_semantics.py` | 3 | Grounded extension: reinstatement chain, attack cycle, simple defeat |
| `tests/test_judge.py` | 3 | Raw probability worked example, zero-signal → 0.5, isotonic monotonicity/bounds |
| `tests/test_calibration.py` | 2 | Calibrator maps raw→calibrated, clips out-of-range inputs |
| `tests/test_grok_client.py` | 6 | Missing-key ValueError, returns content, correct args, non-429 errors raise, transient 429 retries once, daily-quota 429 fails fast |
| `tests/test_orchestrator.py` | 6 | Normal 3-round debate, malformed-JSON recovery, both-exhaust-retries, `on_argument` streams each turn, advocate-concedes-turn-1 (regression), mutual concession early stop |
| `tests/test_fact_checker.py` | 4 | Parses scores, malformed → all-neutral, API error → all-neutral, empty transcript |
| `tests/test_pipeline.py` | 5 | `build_graph` shape + drops dangling edges, `assemble_verdict` no-calibrator, `run_pipeline` updates store, records error |

### 1.6 Backend dependencies (`requirements.txt`, installed versions)

`fastapi 0.141` · `uvicorn 0.52` · `pydantic 2.13` · `pydantic-settings 2.15` ·
`networkx 3.6` · `scikit-learn 1.9` · `openai 3.6` · `pytest 9.1` ·
`rank_bm25 0.2.2` **(installed, unused — reserved for the future BM25 fact-checker)** ·
`matplotlib 3.11` **(installed, unused — reserved for reliability diagrams)**.

---

## 2. Frontend — Current State

> Read this section closely if you're redesigning the UI. The app is small (2 routes, 3
> feature components) and the visual system is deliberate but minimal.

### 2.1 Tech stack

| Concern | Choice | Version | Notes |
|---|---|---|---|
| Framework | **TanStack Start** (React SSR meta-framework, file-based routing) | `@tanstack/react-start` 1.168 | Built by Lovable from the `tanstack_start_ts_current` template. SSR + client hydration. Deploy target is Cloudflare (nitro) but runs fine as `npm run dev`. |
| UI runtime | React | 19.2 | |
| Router | `@tanstack/react-router` | 1.170 | File routes in `src/routes/`, generated `routeTree.gen.ts`. |
| Data fetching | `@tanstack/react-query` | 5.102 | All backend calls go through `useQuery`. Polling via `refetchInterval`. |
| Styling | **Tailwind CSS v4** | 4.3 | v4 = CSS-first config. Single file `src/styles.css` with `@theme inline` tokens + `@layer base`. No `tailwind.config.js`. |
| Icons | `lucide-react` | 0.575 | The only icon source. ~9 icons used: `Scale, ArrowRight, ArrowLeft, Loader2, Radio, TriangleAlert, ShieldCheck, Swords, Network`. |
| Class utility | `clsx` + `tailwind-merge` via `cn()` in `src/lib/utils.ts` | | |
| Build | Vite 8, TypeScript 5.9, Node 22 | | `npm run dev`, `npm run build`, `npm run lint` (eslint 9). |

**Large amounts of dead scaffolding.** `package.json` lists ~40 runtime deps — Radix UI
primitives, `recharts`, `embla-carousel`, `cmdk`, `vaul`, `react-hook-form`, `zod`, `sonner`,
`date-fns`, `react-day-picker`, `input-otp`, `next-themes`, etc. **None of these are imported
by the actual app.** `src/components/ui/` contains **48 shadcn/ui components** (`button.tsx`,
`card.tsx`, `dialog.tsx`, `sidebar.tsx`, …) and `src/hooks/use-mobile.tsx` — **zero are
imported anywhere in `src/routes/` or `src/components/debate/`.** `components.json` (shadcn
config, "new-york" style, base color "slate") is present. A redesign can freely delete
`src/components/ui/`, `src/hooks/`, and prune `package.json` to: react, react-dom, the three
`@tanstack/*` packages, `lucide-react`, `clsx`, `tailwind-merge`, `tailwindcss` + build
tooling. Nothing else is load-bearing.

Also present, Lovable-injected, keep as-is: `src/lib/error-capture.ts`,
`src/lib/error-page.ts`, `src/lib/lovable-error-reporting.ts`, `src/server.ts`,
`src/start.ts` (SSR error handling + CSRF middleware). Not visual.

### 2.2 Component tree

```
src/routes/__root.tsx          RootShell (<html class="dark"> + <head> + fonts) → RootComponent
  └─ QueryClientProvider
     └─ <Outlet/>
        ├─ src/routes/index.tsx            "/"                → ClaimScreen
        └─ src/routes/debate.$debateId.tsx "/debate/$id"      → DebateView
             ├─ header (sticky): back link · debate id · status chip · tab bar
             ├─ (optional) failure banner
             ├─ (optional) claim banner
             └─ tab content:
                  transcript → src/components/debate/TranscriptView.tsx
                                 └─ ArgumentCard ×N  (+ ConfidenceBadge)
                                 └─ live cue row ("<Agent> is forming a rebuttal…" / "Scoring…")
                  graph      → src/components/debate/ArgumentGraph.tsx   (hand-rolled force-directed SVG)
                                 + legend row
                  verdict    → src/components/debate/VerdictPanel.tsx
                                 └─ Gauge (semicircle SVG) + raw/delta stats + grounded-extension chips + explanation
  errorComponent / notFoundComponent: centered 404 / "This page didn't load" cards
```

Only **3 feature components** exist, all in `src/components/debate/`. Everything else in the
tree is route-level JSX.

### 2.3 The two screens — detailed visual description

Both screens render on a **dark slate background** (`oklch(0.17 0.014 260)` ≈ very dark
des-blue-grey) with a faint 44px dotted grid overlay (`grid-backdrop` utility) on the
landing page and inside the graph panel. Body font is **Space Grotesk**; all labels, chips,
ids, and numbers are **IBM Plex Mono**, frequently uppercase with wide letter-spacing
(`tracking-[0.18em]`). The aesthetic is "analytical terminal / research dashboard".

#### Screen 1 — Claim entry (`/`, `ClaimScreen`)

Single centered column, `max-w-3xl`, vertically centered in the viewport, `px-6 py-16`.
Top to bottom:

1. **Eyebrow chip** — small bordered pill, mono uppercase: `⚖ Dialectic · academic demo`.
2. **H1** — "Debate-based fact verification", `text-4xl font-semibold`.
3. **Sub-paragraph** — one muted sentence explaining the mechanic ("Two agents argue a claim
   across structured rounds. Attacks form an argumentation framework; the grounded extension
   and a calibrated probability form the verdict.").
4. **Claim form** — a bordered rounded card (`bg-card`, slightly lighter than the page). Mono
   uppercase label "CLAIM"; a 3-row `<textarea>` (no resize) with placeholder "Enter a
   factual claim to put under adversarial scrutiny…"; a footer row with `rounds = 2` on the
   left (mono, muted) and a cyan **"→ Start Debate"** button on the right (disabled until the
   textarea is non-empty; shows a spinner while the POST is in flight, then navigates to
   `/debate/<id>`).
5. **"TRY ONE"** — mono uppercase label, then 3 full-width bordered buttons with example
   claims. Clicking one fills the textarea (does not submit).
6. **"OR OPEN A CACHED DEBATE (INSTANT, NO RATE LIMIT)"** — 3 full-width bordered links to
   the pre-seeded demo debates (`demo-sea-level`, `demo-rust-memory`, `demo-llm-verify`),
   labelled e.g. "Sea level rise has accelerated (advocate wins)".
7. **Feature triptych** — a 3-column grid of small bordered cards, each a lucide icon
   (`ShieldCheck` / `Swords` / `Network`) + title ("Advocate" / "Skeptic" / "Attack graph")
   + one muted line.

#### Screen 2 — Debate view (`/debate/$debateId`, `DebateView`)

Full-width, `max-w-6xl` centered content. A **sticky top header** (translucent, blurred):
- left: `← new claim` link (mono), then `debate/<id>` (mono, muted)
- if the frontend fell back to bundled mock data because the backend was unreachable: an
  amber chip `demo data · backend offline`
- right: a status chip — one of:
  `⚠ failed` (amber) · `◉ live · polling` (cyan, pulsing dot) · `complete` (grey)
- below, flush with the header bottom border: a **tab bar** with 3 mono-uppercase tabs —
  `TRANSCRIPT` · `GRAPH` · `VERDICT` — active tab underlined in cyan.

Body (`px-6 py-8`):
- If the debate errored: a **failure banner** — amber-bordered card, "⚠ DEBATE FAILED", the
  backend's error message, and a line pointing to the cached demos.
- Once the verdict exists: a **claim banner** — left cyan border rule, mono "CLAIM" label,
  the claim text.
- Then the active tab's content.

**TRANSCRIPT tab** (`TranscriptView`):
Arguments grouped by round. Each round: a mono "Round N" label with a horizontal rule, then
a **2-column grid — advocate arguments in the left column, skeptic in the right.** Each
argument is an **`ArgumentCard`**: a bordered rounded card (`bg-card`), border tinted
cyan (advocate) or amber (skeptic). Card header row: a coloured agent pill with icon
(`ShieldCheck`/`Swords`) + agent name, the `#arg_N` id (mono muted), a `conf 0.85` badge, and
— once the verdict is in — a green `survived` badge if the argument is in the grounded
extension. Card body: the argument text (`text-sm leading-relaxed`). Footer, if any:
`attacks → arg_2` (mono muted). Cards are buttons; clicking one sets a `selected` id that
cross-highlights it here and in the graph (via a `ring`).
While the debate is streaming, a **dashed live-cue row** appears below the last card:
`⟳ Advocate is forming a rebuttal…` (in that agent's colour) between turns, then
`⟳ Scoring the argument graph…` (grey) while the verdict computes. Empty in-progress state:
`⟳ Debate in progress — waiting for the first argument…`.

**GRAPH tab** (`ArgumentGraph`):
A `640×420` viewBox `<svg>` in a bordered panel with the dotted-grid background. **Hand-rolled
force-directed layout** — nodes seeded on a circle, then relaxed each animation frame with
repulsion + edge springs + gentle centering, damping to rest (`requestAnimationFrame` loop,
no library). **Advocate nodes are cyan circles, skeptic nodes are amber rounded squares.**
Each node shows its id (`ARG_1`, mono) and `r1`/`r2` round label below it. A node in the
grounded extension gets a **dashed green ring**. Edges are grey lines with arrowheads
(attacker → target). Clicking a node sets the shared `selected` id (thicker stroke). Below
the SVG: a legend row (advocate / skeptic / survived / "arrow = attacks"). The graph
`refetch`es every 1.5 s while the debate is in progress, so it visibly grows.

**VERDICT tab** (`VerdictPanel`):
- Top card: on the left, a **semicircular gauge** (hand-drawn SVG arc) filled to
  `calibrated_probability`, green if ≥ 0.5 else amber, with the percentage in large mono
  numerals in the middle. On the right: "RAW PROBABILITY" (e.g. `41.0%`) and "CALIBRATION
  DELTA" (e.g. `+0.0 pts`, green if ≥ raw else amber — currently always `+0.0` since the
  calibrator is untrained).
- A 2-column grid: **"GROUNDED · ADVOCATE"** and **"GROUNDED · SKEPTIC"** cards, each listing
  the surviving argument ids as small coloured chips, or "none survived".
- **"EXPLANATION"** card: the backend's generated paragraph — states which side's arguments
  survived the grounded extension, that the judge combined structural + fact-check +
  confidence signals into `P(claim true) = X`, and that no calibrator is trained yet so
  calibrated = raw.

### 2.4 Design tokens (`src/styles.css`)

**Dark theme only.** `<html class="dark">` is hard-coded in `__root.tsx`; there is no theme
toggle and no light palette. All colours are **oklch** CSS custom properties on `:root`,
exposed to Tailwind via `@theme inline` (so `bg-card`, `text-advocate`, `border-skeptic/40`
etc. all work).

| Token | Value (oklch) | Reads as | Used for |
|---|---|---|---|
| `--background` | `0.17 0.014 260` | near-black blue-grey | page background |
| `--foreground` | `0.95 0.006 260` | near-white | body text |
| `--surface` | `0.21 0.016 260` | dark grey | inputs, secondary surfaces |
| `--surface-raised` | `0.25 0.018 260` | slightly lighter | badges |
| `--card` | `0.21 0.016 260` | dark grey | cards |
| `--border` | `0.31 0.017 260` | mid grey | all borders (also applied to `*` in base layer) |
| `--primary` / `--ring` | `0.78 0.13 197` / `0.7 0.11 197` | **cyan** | primary buttons, active tab, focus |
| `--advocate` | `0.79 0.13 197` | **cyan** | advocate agent everywhere |
| `--advocate-soft` | `0.28 0.05 210` | dim cyan | advocate pill bg |
| `--skeptic` | `0.81 0.14 76` | **amber/gold** | skeptic agent; also reused for warnings/failures |
| `--skeptic-soft` | `0.30 0.05 78` | dim amber | skeptic pill bg |
| `--survived` | `0.78 0.16 152` | **green** | grounded-extension survivor markers, gauge ≥50% |
| `--destructive` | `0.62 0.2 22` | red | defined, not currently used in the app |
| `--radius` | `0.5rem` | | base radius; `-sm/-md/-lg/-xl/-2xl` derived |

**Typography:** `--font-sans` = `"Space Grotesk", ui-sans-serif, system-ui` ·
`--font-mono` = `"IBM Plex Mono", ui-monospace`. Both loaded from Google Fonts in
`__root.tsx` (Space Grotesk 400–700, IBM Plex Mono 400/500). Mono is used heavily for
chrome: labels, ids, numbers, tab names, chips — almost always `text-[11px]` or `text-xs`,
`uppercase`, `tracking-[0.14em]`–`[0.18em]`.

**Custom utility:** `grid-backdrop` — a 44px dotted grid via layered linear-gradients at 3%
white opacity.

### 2.5 Data flow (backend → frontend)

**Polling only. No WebSockets, no SSE.** All via `@tanstack/react-query` in
`src/lib/api.ts` (`startDebate`, `getTranscript`, `getGraph`, `getVerdict`) →
`DebateView`'s three `useQuery` hooks.

| Query | Trigger | Refetch |
|---|---|---|
| `["transcript", id]` | on mount | every **1.5 s while `status === "in_progress"`**, then stops |
| `["graph", id]` | on mount | every 1.5 s while the transcript is in progress, then stops |
| `["verdict", id]` | **enabled only once `transcript.status === "complete"`** | one-shot |

`startDebate` is a `POST` fired from the landing page; on success it navigates to the debate
route with the returned id.

**`src/lib/api.ts` behaviour to know:** a `request()` wrapper distinguishes two failure
modes — (a) `fetch` throws (backend genuinely unreachable) → falls back to bundled
`src/lib/mock-data.ts` and sets `apiState.usingMock = true` (drives the "backend offline"
chip); (b) the backend returns an HTTP error status → throws a typed `ApiError` and does
**not** show mock data (so a rate-limited live debate shows a real failure, not a fake
result). React Query is told not to retry `ApiError`s.

### 2.6 What's live vs static

| Element | Behaviour |
|---|---|
| Transcript | **Streams in turn by turn.** Backend writes each argument to the store as the LLM produces it; the 1.5 s poll reveals them incrementally. ~2 s/turn on `gemini-3.5-flash-lite`, so a 2-round debate fully populates in ~10 s. |
| Attack graph | **Grows live** alongside the transcript (same poll cadence); force sim re-lays-out as nodes appear. |
| Live cue row | Updates between turns ("<Agent> is forming a rebuttal…" → "Scoring the argument graph…"). |
| Status chip | `live · polling` → `complete` / `failed`. |
| Verdict | **One-shot** — fetched once when the debate completes. Gauge/stats/chips do not animate in (they just appear). |
| Claim banner | Appears only after the verdict loads (it reads `verdict.data.claim`). |
| Cached demo debates | Load instantly, fully complete, no polling. |

### 2.7 Known UI rough edges / bugs

- **`src/components/ui/` (48 shadcn components) and `src/hooks/use-mobile.tsx` are entirely
  unused.** Dead weight; ~35 unused npm deps behind them.
- **Desktop-only in practice.** Almost no responsive work (see §2.8).
- **Graph SVG is a fixed `640×420` viewBox** — it scales to container width but on a narrow
  screen the nodes are tiny and the force layout crowds; there's no zoom/pan.
- **Verdict claim banner only shows after the verdict loads** — during a live debate the
  claim text is nowhere on the debate screen (only the id is shown). Minor context gap.
- The **live cue "Advocate/Skeptic is forming a rebuttal"** infers the next speaker from
  `arguments.length % 2` — correct for clean debates, can briefly mislabel if an agent
  conceded a turn.
- **No empty/hover/focus polish on the graph nodes** beyond a stroke-width bump on select.
- **Product naming is inconsistent.** The page `<title>`, meta, and the landing-page eyebrow
  chip all say **"Dialectic"** (an earlier working name); the repo and other docs say
  **"Argus"**; the backend FastAPI title says "Argus Debate System". A `favicon.ico` exists
  (Lovable default). Pick one name during the redesign.
- The 404 and root error-boundary screens use a **different visual style** (plain centered
  card, `bg-primary` solid button) than the rest of the app — they're template defaults.
- No loading skeletons — just a centered `⟳ Loading…` line.

### 2.8 Responsiveness

**Effectively desktop-first / desktop-only.** Total responsive breakpoint usage in the app
code: one `md:grid-cols-2` (transcript columns), a handful of `sm:` utilities in the verdict
top card, and `sm:grid-cols-3` on the landing triptych. That's it.
- On mobile the transcript collapses to one column (fine), but the **sticky header wraps
  awkwardly** (back-link + id + chip + 3 tabs all `flex-wrap` with no mobile treatment).
- The **graph tab is not usable on a phone** (fixed aspect SVG, tiny nodes, no pan/zoom).
- The landing column is `max-w-3xl` centered — acceptable on mobile but untested.
- No hamburger, no drawer, no mobile nav. No `@media` tuning beyond Tailwind defaults.
- Never tested at mobile widths this project.

---

## 3. Data Models

These are the exact shapes available to any UI. Backend = Pydantic (`app/models/schemas.py`);
frontend = TypeScript (`src/lib/types.ts`). They match 1:1 except where noted.

```ts
// The atom of a debate. One move by one agent.
interface Argument {
  id: string;                       // "arg_1", "arg_2", …
  agent: "advocate" | "skeptic";
  round: number;                    // 1-indexed
  text: string;                     // the argument prose (1–4 sentences typically)
  attacks: string[];                // ids of arguments this one attacks (0 or 1 in practice)
  self_confidence: number;          // 0..1, the agent's own claim — uncalibrated, treat as a weak signal
}

// GET /debate/{id}/transcript
interface Transcript {
  arguments: Argument[];            // grows over polls while status === "in_progress"
  status: "in_progress" | "complete";
  rounds: number;                   // total rounds the debate will run (2 by default)
}

// GET /debate/{id}/verdict
interface Verdict {
  claim: string;
  raw_probability: number;          // 0..1 — judge output before calibration
  calibrated_probability: number;   // 0..1 — currently ALWAYS == raw_probability (no trained calibrator)
  grounded_extension: {
    advocate: string[];             // ids of advocate arguments that survived
    skeptic: string[];              // ids of skeptic arguments that survived
  };
  explanation: string;              // generated paragraph, safe to render verbatim
}

// GET /debate/{id}/graph  (nodes/edges derived from the transcript)
interface GraphNode {
  id: string;                       // === Argument.id
  agent: "advocate" | "skeptic";
  round: number;
  label: string;                    // "ARG_1" (id uppercased)
}
interface GraphEdge {
  source: string;                   // attacker argument id
  target: string;                   // attacked argument id
}
interface DebateGraph { nodes: GraphNode[]; edges: GraphEdge[]; }

// POST /debate/start
interface StartDebateRequest  { claim: string; rounds?: number; }   // frontend sends rounds: 2
interface StartDebateResponse { debate_id: string; }                // "debate-<12 hex>"

// Backend-internal only (not exposed by any endpoint), app/services/debate_store.py
interface DebateRecord {
  debate_id: string; claim: string; rounds: number;
  status: "in_progress" | "complete" | "error";
  transcript: Argument[];
  verdict: Verdict | null;
  graph: DebateGraph | null;
  error: string | null;             // friendly message when status === "error"
}

// Backend-internal, produced by the fact-checker, consumed by the judge. Not in any response.
interface FactCheckResult {
  argument_id: string;
  evidence_sentences: string[];     // currently holds the one-line LLM "reasoning", or []
  support_score: number;            // -1 (contradicted) .. +1 (supported), 0 = neutral/unknown
}
```

**Data a new UI could surface that the current one doesn't:** per-argument
`self_confidence` is shown but the fact-check `support_score` / `reasoning` per argument is
**computed and fed to the judge but never sent to the client** — exposing it (endpoint change)
would let the UI show "the fact-checker rated this argument −0.4" next to each card. The
`round` on every node/argument enables a timeline view. `rounds` (total) enables a progress
indicator.

---

## 4. What's Deliberately Not Done Yet

From `PROJECT_STATE.md` + direct code inspection:

| Area | State | Note |
|---|---|---|
| **FEVER dataset** | Not integrated. `data/` holds only `demo_debates.json`. | The eval plan (PRD §6, §11) is to run ~50–100 labelled FEVER claims. |
| **Trained calibrator** | `fit_calibrator`/`apply_calibration` work and are tested, but `data/calibrator.pkl` doesn't exist. | `calibrated_probability == raw_probability` everywhere today. Needs labelled data (FEVER) to train. This is the "M7 Learning" deliverable. |
| **Evaluation pipeline** | Not started. | Baseline (single LLM call) vs full system: accuracy + **ECE (Expected Calibration Error)** + reliability diagrams. `matplotlib` is pre-installed for this. This is the headline metric that makes the project defensible. |
| **Symbolic fact-checker** | Replaced with an LLM call for now. | PRD §5d wants BM25 retrieval (`rank_bm25`, pre-installed) + (subject,predicate,object) triple extraction + forward-chaining contradiction detection against an evidence corpus. Current version is one LLM judgment call, no retrieval, no KB. |
| **Persistence** | In-memory dict only. | Fine for the demo; `debate_store` would need a real store (SQLite/Redis) for anything multi-process or restart-surviving. |
| **Planning module (M6)** | Not built. | A "debate-strategy planner" (sequence which arguments to raise based on opponent weak points) was floated as optional syllabus coverage, not committed. |
| **Frontend: unused scaffold** | `src/components/ui/` (48 files), `src/hooks/`, ~35 npm deps. | Lovable template leftovers. Safe to delete wholesale. |
| **Auth / rate limiting / multi-user** | None. | Single-user local demo. |
| **Deploy** | Not deployed. Frontend build targets Cloudflare via nitro; backend has no deploy config. | |

**Scaffolded-but-wired (works, just thin):** the calibration code path (loads a pkl that
isn't there → falls through to identity), the `check_argument` single-arg wrapper (works,
nothing calls it), `GraphResponse` on-the-fly build for partial transcripts (works, used by
the live graph).

---

## 5. Repo Info

### Run it locally

**Backend** (Python 3.11 — *not* the Windows Store Python alias):
```powershell
cd C:\AI-Project
py -3.11 -m venv venv                 # first time only
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt       # first time only
copy .env.example .env                # then edit .env with a real LLM_API_KEY
uvicorn app.main:app --port 8000
```
API at `http://127.0.0.1:8000`, interactive docs at `/docs`. Startup log line
`Loaded 3 cached demo debate(s)` confirms the demo seed.

**Frontend** (Node 22, separate terminal — the backend blocks its own terminal):
```powershell
cd C:\AI-Project\frontend
npm install                           # first time only
npm run dev
```
Vite prints a `http://localhost:<port>` URL (has been `8080` and `5173` depending on
what's free). Expects the backend at `http://localhost:8000` (override with
`VITE_API_BASE_URL`).

**Tests:**
```powershell
cd C:\AI-Project
.\venv\Scripts\python.exe -m pytest -v     # 32 passed, 0 skipped
cd frontend; npx tsc --noEmit              # frontend typecheck
```

**Free port 8000 if a stray server holds it** (common — an unactivated-venv run leaks one):
```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

### Git

- **Branch:** `master` (also the main branch; no other branches in use).
- **Remote:** `https://github.com/piyush-bhutra/Argus.git`
- **Recent commits (newest first):**
  ```
  ab2bcd6  docs: note live argument streaming in PROJECT_STATE
  e9b8995  Stream debate arguments into the transcript as they arrive
  f44785c  Handle LLM rate limits honestly; move to gemini-3.5-flash-lite
  db08825  Wire debate pipeline end-to-end and switch LLM provider to Gemini
  1fabc85  Implement Grok client and orchestrator, plus CORS and Judge updates
  50eacab  docs: update README with frontend setup and module mapping
  0f27af0  feat(frontend): integrate React dashboard for UI visualization
  f62609c  Implement grounded extension semantics
  92b7466  Initial Commit - project scaffolding
  ```
- **Recent direction:** the last four commits took the project from "four components that
  never ran together + a mock-data frontend" to a working end-to-end system: wired the
  pipeline into real API routes, added in-memory persistence + background execution, swapped
  the dead LLM provider (Cerebras → Gemini) behind an env-configurable base URL, made
  rate-limit failures honest in the UI, and made the transcript stream in turn-by-turn
  instead of appearing all at once.

### Other docs in the repo

- `debate_system_prd.md` — the full product/technical spec (component-by-component).
- `PROJECT_STATE.md` — the living status doc (some spots slightly lag this snapshot).
- `DEMO.md` — Review-1 demo script + viva prep (grounded-extension by hand, judge math).
- `status_report_2026-08-29.md` — a pre-wiring automated analysis (historical).
- `scripts/build_offline_demos.py` — regenerates `data/demo_debates.json` deterministically
  (hand-authored transcripts, no LLM). `scripts/seed_demos.py` — same but from real live
  debates.
