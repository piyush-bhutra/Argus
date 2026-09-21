import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { MOCK_CLAIM } from "@/lib/mock-data";
import { DEFAULT_ROUNDS, Mono, primaryButton, useStartDebate } from "@/components/debate/paper";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Argus" },
      {
        name: "description",
        content:
          "Run adversarial advocate-vs-skeptic debates over a claim, inspect the argument attack graph, and read a calibrated verdict.",
      },
      { property: "og:title", content: "Argus — Debate-Based Fact Verification" },
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

const listItem =
  "block w-full rounded-paper border border-dashed border-hairline-dashed bg-paper-card/80 px-3 py-2 text-left text-body-sm text-ink-soft transition-colors hover:border-ink-strong hover:text-ink-strong";

function ClaimScreen() {
  const [claim, setClaim] = useState("");
  const { start, pending } = useStartDebate();

  return (
    <main className="paper-ruled min-h-screen font-hand text-ink">
      <div className="mx-auto max-w-shell px-5">
        <div className="max-w-[820px] py-[74px]">
          <Mono className="tracking-data-wide">
            MULTI-AGENT DEBATE · GROUNDED EXTENSION · CALIBRATED P(TRUE)
          </Mono>
          <h1 className="mt-2.5 mb-1.5 font-marker text-hero tracking-[1px] text-ink-strong">
            Argus
          </h1>
          <p className="mb-7 max-w-[640px] text-lead text-pretty text-ink-soft">
            An Advocate and a Skeptic argue your claim across rounds. An argumentation engine
            decides which arguments structurally survive — then the judge hands back a calibrated
            probability.
          </p>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              void start(claim);
            }}
            className="relative rounded-paper border-[1.5px] border-ink-strong bg-paper-card p-4 shadow-card"
          >
            <label htmlFor="claim" className="mb-2 block">
              <Mono>CLAIM UNDER EXAMINATION</Mono>
            </label>
            <textarea
              id="claim"
              rows={3}
              value={claim}
              onChange={(e) => setClaim(e.target.value)}
              placeholder="Type a factual claim to verify…"
              className="claim-lines w-full resize-y border-0 bg-transparent p-0 font-hand text-claim text-ink outline-none placeholder:text-ink-ghost"
            />
            <div className="mt-3.5 flex flex-wrap items-center gap-4">
              <button
                type="submit"
                disabled={!claim.trim() || pending}
                className={cn(primaryButton, "px-6 pt-2.5 text-[29px]")}
              >
                {pending ? "Starting…" : "Start Debate"}
              </button>
              <Mono>{DEFAULT_ROUNDS} ROUNDS · ADVOCATE VS SKEPTIC · ATTACK GRAPH</Mono>
            </div>
          </form>

          <div className="mt-8 grid grid-cols-[repeat(auto-fit,minmax(290px,1fr))] gap-6">
            <div>
              <Mono className="tracking-[.16em]">TRY ONE</Mono>
              <div className="mt-2 flex flex-col gap-2">
                {EXAMPLES.map((ex) => (
                  <button key={ex} type="button" onClick={() => setClaim(ex)} className={listItem}>
                    {ex}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <Mono className="tracking-[.16em]">
                OR OPEN A CACHED DEBATE · INSTANT, NO RATE LIMIT
              </Mono>
              <div className="mt-2 flex flex-col gap-2">
                {CACHED_DEMOS.map((d) => (
                  <Link
                    key={d.id}
                    to="/debate/$debateId"
                    params={{ debateId: d.id }}
                    className={listItem}
                  >
                    {d.label}
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
