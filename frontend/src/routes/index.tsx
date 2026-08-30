import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { ArrowRight, Loader2, Network, Scale, ShieldCheck, Swords } from "lucide-react";
import { startDebate } from "@/lib/api";
import { MOCK_CLAIM } from "@/lib/mock-data";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Dialectic — Debate-Based Fact Verification" },
      {
        name: "description",
        content:
          "Run adversarial advocate-vs-skeptic debates over a claim, inspect the argument attack graph, and read a calibrated verdict.",
      },
      { property: "og:title", content: "Dialectic — Debate-Based Fact Verification" },
      {
        property: "og:description",
        content:
          "Adversarial multi-agent debate for claim verification: transcript, attack graph, and calibrated probability.",
      },
    ],
  }),
  component: ClaimScreen,
});

const EXAMPLES = [
  MOCK_CLAIM,
  "Global sea level rise has accelerated over the past three decades.",
  "Rust eliminates all classes of memory-safety bugs in production systems.",
];

// Pre-cached debates seeded into the backend (data/demo_debates.json). These
// render instantly with no LLM calls — use them when the rate limit bites.
const CACHED_DEMOS = [
  { id: "demo-sea-level", label: "Sea level rise has accelerated (advocate wins)" },
  { id: "demo-rust-memory", label: "Rust eliminates all memory-safety bugs (skeptic wins)" },
  { id: "demo-llm-verify", label: "LLMs can verify facts without retrieval (skeptic wins)" },
];

const ROUNDS = 2;

function ClaimScreen() {
  const navigate = useNavigate();
  const [claim, setClaim] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!claim.trim() || pending) return;
    setPending(true);
    try {
      const { debate_id } = await startDebate(claim.trim(), ROUNDS);
      navigate({ to: "/debate/$debateId", params: { debateId: debate_id } });
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="grid-backdrop min-h-screen">
      <div className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-6 py-16">
        <div className="mb-10">
          <div className="mb-4 inline-flex items-center gap-2 rounded border border-border bg-surface px-2 py-1 font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            <Scale className="size-3" /> Dialectic · academic demo
          </div>
          <h1 className="text-4xl font-semibold tracking-tight">
            Debate-based fact verification
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted-foreground">
            Two agents argue a claim across structured rounds. Attacks form an argumentation
            framework; the grounded extension and a calibrated probability form the verdict.
          </p>
        </div>

        <form onSubmit={submit} className="rounded-xl border border-border bg-card p-5">
          <label
            htmlFor="claim"
            className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground"
          >
            Claim
          </label>
          <textarea
            id="claim"
            value={claim}
            onChange={(e) => setClaim(e.target.value)}
            rows={3}
            placeholder="Enter a factual claim to put under adversarial scrutiny…"
            className="mt-2 w-full resize-none rounded-lg border border-input bg-surface px-3 py-2.5 text-sm outline-none placeholder:text-muted-foreground/70 focus:border-ring"
          />
          <div className="mt-4 flex items-center justify-between gap-4">
            <span className="font-mono text-[11px] text-muted-foreground">rounds = {ROUNDS}</span>
            <button
              type="submit"
              disabled={!claim.trim() || pending}
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              {pending ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
              Start Debate
            </button>
          </div>
        </form>

        <div className="mt-5">
          <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            Try one
          </div>
          <div className="mt-2 space-y-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                type="button"
                onClick={() => setClaim(ex)}
                className="block w-full rounded-lg border border-border bg-surface px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:border-ring hover:text-foreground"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-5">
          <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            Or open a cached debate (instant, no rate limit)
          </div>
          <div className="mt-2 space-y-2">
            {CACHED_DEMOS.map((d) => (
              <Link
                key={d.id}
                to="/debate/$debateId"
                params={{ debateId: d.id }}
                className="block w-full rounded-lg border border-border bg-surface px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:border-ring hover:text-foreground"
              >
                {d.label}
              </Link>
            ))}
          </div>
        </div>

        <div className="mt-10 grid gap-3 sm:grid-cols-3">
          {[
            { icon: ShieldCheck, label: "Advocate", desc: "Builds the case for the claim" },
            { icon: Swords, label: "Skeptic", desc: "Attacks weak premises each round" },
            { icon: Network, label: "Attack graph", desc: "Grounded extension decides survivors" },
          ].map(({ icon: Icon, label, desc }) => (
            <div key={label} className="rounded-lg border border-border bg-card p-3">
              <Icon className="size-4 text-primary" />
              <div className="mt-2 text-sm font-medium">{label}</div>
              <div className="text-xs text-muted-foreground">{desc}</div>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
