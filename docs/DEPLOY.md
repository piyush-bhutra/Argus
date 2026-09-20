# Deploying Argus

Two pieces: a FastAPI backend and a React frontend. The backend ships with 53
precomputed debates baked into the image, so **the deployed demo works with no
API key and no quota at all**. Live debate is an extra, not a dependency.

That is deliberate. A live demo on a free LLM tier returns 429 in front of
whoever is watching; the evaluation run already produced 50 fully traced real
debates, so the deployed app serves those.

---

## What you need

| | |
|---|---|
| A container host | Render, Hugging Face Spaces, Fly, or Railway — all have a usable free tier |
| A frontend host | Cloudflare Pages (the repo is already Lovable/Cloudflare-shaped) or the same container |
| An LLM API key | **Optional.** Only needed for live debate; the demo corpus does not use it |

Nothing else. No database, no object storage, no queue — debate state is
in-process by design (`app/services/debate_store.py`).

---

## 1. Backend

The `Dockerfile` at the repo root builds a single image that any container host
can run. It copies `data/` in, so the evidence corpus and demo debates travel
with the image.

```bash
docker build -t argus .
docker run -p 8000:8000 argus
```

The host injects its own port via `$PORT`; the image falls back to 8000.

### Environment variables

| Variable | Required | Notes |
|---|---|---|
| `CORS_ORIGINS` | **Yes** | The deployed frontend's origin, e.g. `https://argus.pages.dev`. Comma-separated for several. Defaults to `*`, which works but allows any site to call the API |
| `DEBATE_RATE_LIMIT` | No | Debates one caller may start per window. Default **5**. Set `0` to disable live debate entirely and serve demos only |
| `DEBATE_RATE_WINDOW_SECONDS` | No | Default **300** (5 minutes) |
| `TRUST_PROXY_HEADERS` | No | Default `false`. Set `true` **only** behind a proxy that overwrites `X-Forwarded-For`; otherwise a caller can spoof the header and bypass the rate limit |
| `LLM_API_KEY` | No | Set as a **secret**, never as a plain env var. Omit to run demo-only |
| `LLM_MODEL` | No | e.g. `gemini-3.5-flash-lite` |
| `LLM_BASE_URL` | No | e.g. `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `LOG_DIR` | No | Defaults to `/tmp/logs` in the image |

`.env` is git-ignored and is **not** in the image. Set these in the host's own
secret store.

### Host-specific notes

- **Render** — New → Web Service → point at the repo → it detects the
  Dockerfile. Free instances sleep after inactivity, so the first request after
  a pause takes ~30 s. Set a health check path of `/health`.
- **Hugging Face Spaces** — create a Docker Space and push the repo. Spaces
  expect port 7860, so set `PORT=7860`. Secrets go in Settings → Variables and
  secrets.
- **Fly / Railway** — `fly launch` / connect the repo; both read the Dockerfile
  and provide `$PORT` automatically.

### Verify the deployment

```bash
curl https://<your-backend>/health
```

```json
{"status":"ok","llm_configured":false,"evidence_corpus":true,"demo_debates":53}
```

`evidence_corpus: true` and `demo_debates: 53` confirm `data/` made it into the
image. If either is wrong the demo will look empty, and this endpoint is how you
find that out before a viewer does. `llm_configured: false` is fine and expected
when running demo-only.

---

## 2. Frontend

```bash
cd frontend
npm install
npm run build          # outputs .output/
```

Set **`VITE_API_BASE_URL`** to the backend origin (no trailing slash) as a
build-time variable, then deploy `.output/` to Cloudflare Pages. It defaults to
`http://localhost:8000`, so a build without it will fail to reach the API from a
deployed page.

Note that Vite bakes this in at **build** time, not run time: changing it on the
host requires a rebuild, not just a restart.

If the backend is unreachable the frontend falls back to bundled mock data and
sets `apiState.usingMock`, so a broken deployment shows a plausible-looking
debate rather than an error. Confirm `/health` from the browser's own origin
before believing what you see.

**Guardrail:** `frontend/AGENTS.md` records that this repo is connected to
Lovable. Do not force-push or rewrite published history on the connected
branch — it rewrites history on Lovable's side and loses project history.

---

## 3. Checklist

- [ ] Backend deployed; `/health` returns `demo_debates: 53`
- [ ] `CORS_ORIGINS` set to the frontend's real origin, not `*`
- [ ] `LLM_API_KEY` set as a **secret** if live debate is wanted, otherwise omitted
- [ ] `DEBATE_RATE_LIMIT` considered — `0` serves demos only and cannot spend quota
- [ ] `TRUST_PROXY_HEADERS` left `false` unless a proxy overwrites `X-Forwarded-For`
- [ ] `python -m pip_audit` clean against the committed `requirements.txt`
- [ ] Frontend built and pointed at the backend origin
- [ ] A demo debate opens and renders its evidence trace, e.g.
      `/debate/demo-danger-uxb-is-from-1981`
- [ ] Live debate either works, or fails with the honest quota message rather
      than a blank screen (`_friendly_error` in `app/services/pipeline.py`)

---

## 4. Refreshing the demo corpus

The demo debates are generated from the evaluation cache, so they update with
the system:

```bash
python -m scripts.export_demos --keep-existing
```

Re-runnable safely — it deduplicates on claim text, so running it twice does not
double the corpus. Rebuild and redeploy the image afterwards.

---

## 5. Known constraints

- **In-memory state.** Live debates are lost on restart; the demo corpus reloads
  from disk at startup. Fine for a demo, not for production traffic.
- **No authentication.** The API is open by design (it has no user accounts).
  Live debate is rate limited to 5 starts per caller per 5 minutes, because each
  start spends roughly six LLM requests on your key — without that cap the
  endpoint is an open LLM proxy onto your quota.

  The limit is **per process**, so it resets on restart and each instance gets
  its own budget if you scale out. If you put a **paid** key behind a public
  URL, add a limit at the proxy or CDN too, and consider `DEBATE_RATE_LIMIT=0`
  to serve the demo corpus only.
- **Free-tier sleep.** Render and similar suspend idle instances; expect a cold
  start on the first request.
