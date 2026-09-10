import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiError, apiState, getGraph, getTranscript, getVerdict } from "@/lib/api";
import type { Verdict } from "@/lib/types";
import { TranscriptView } from "@/components/debate/TranscriptView";
import { ArgumentGraph } from "@/components/debate/ArgumentGraph";
import { VerdictPanel } from "@/components/debate/VerdictPanel";
import {
  CueRow,
  LockedPanel,
  Mono,
  SectionHeader,
  primaryButton,
  readStoredClaim,
  secondaryButton,
  useStartDebate,
} from "@/components/debate/paper";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/debate/$debateId")({
  head: () => ({
    meta: [
      { title: "Argus — Debate" },
      {
        name: "description",
        content:
          "Live advocate-vs-skeptic transcript, argument attack graph, and calibrated verdict for a single claim.",
      },
      { property: "og:title", content: "Argus — Debate" },
      {
        property: "og:description",
        content: "Transcript, attack graph, and calibrated verdict for a verified claim.",
      },
    ],
  }),
  component: DebateView,
});

type Status = "pending" | "running" | "done" | "failed";
const SECTIONS = ["claim", "debate", "graph", "ruling"] as const;
type Section = (typeof SECTIONS)[number];

function DebateView() {
  const { debateId } = Route.useParams();

  const transcript = useQuery({
    queryKey: ["transcript", debateId],
    queryFn: () => getTranscript(debateId),
    // Poll quickly while the debate streams in so arguments appear turn by turn.
    refetchInterval: (q) => (q.state.data?.status === "in_progress" ? 1500 : false),
    retry: (count, err) => !(err instanceof ApiError) && count < 2,
  });

  const inProgress = transcript.data?.status === "in_progress";

  const graph = useQuery({
    queryKey: ["graph", debateId],
    queryFn: () => getGraph(debateId),
    // Grow the attack graph live alongside the transcript.
    refetchInterval: inProgress ? 1500 : false,
    retry: (count, err) => !(err instanceof ApiError) && count < 2,
  });
  const verdict = useQuery({
    queryKey: ["verdict", debateId],
    queryFn: () => getVerdict(debateId),
    enabled: transcript.data?.status === "complete",
    retry: (count, err) => !(err instanceof ApiError) && count < 2,
  });

  const failed = transcript.isError;
  const failureMessage =
    transcript.error instanceof ApiError && transcript.error.message
      ? transcript.error.message
      : "The debate could not be completed — the LLM provider is rate-limited or out of quota.";

  const survivors = new Set([
    ...(verdict.data?.grounded_extension.advocate ?? []),
    ...(verdict.data?.grounded_extension.skeptic ?? []),
  ]);

  const args = transcript.data?.arguments ?? [];
  const complete = transcript.data?.status === "complete";
  // Turns alternate advocate -> skeptic; guess who speaks next for the live cue.
  const nextAgent = args.length % 2 === 0 ? "Advocate" : "Skeptic";
  const expectedTurns = (transcript.data?.rounds ?? 0) * 2;
  const awaitingNextTurn = inProgress && args.length > 0 && args.length < expectedTurns;

  // The transcript doesn't carry the claim; the landing page stores it at start.
  const [storedClaim, setStoredClaim] = useState<string | null>(null);
  useEffect(() => setStoredClaim(readStoredClaim(debateId)), [debateId]);
  const claim = verdict.data?.claim ?? storedClaim ?? "";

  const { start, pending } = useStartDebate();

  const status: Record<Section, Status> = {
    claim: "done",
    debate: failed ? "failed" : !transcript.data ? "pending" : inProgress ? "running" : "done",
    graph: verdict.data ? "done" : (graph.data?.nodes.length ?? 0) > 0 ? "running" : "pending",
    ruling: verdict.data ? "done" : complete ? "running" : "pending",
  };

  const transcriptStatus = failed
    ? "FAILED"
    : !transcript.data
      ? "LOADING"
      : inProgress
        ? "STREAMING · LIVE"
        : `COMPLETE · ${transcript.data.rounds} ROUNDS · ${args.length} ARGUMENTS`;

  return (
    <main className="paper-ruled min-h-screen font-hand text-ink">
      <ClaimStickyBar
        claim={claim}
        debateId={debateId}
        verdict={verdict.data}
        failed={failed}
        inProgress={inProgress}
        loaded={!!transcript.data}
        onRestart={start}
        pending={pending}
      />
      <ProgressRail status={status} />

      <section id="sec-debate" className="mx-auto max-w-shell scroll-mt-[120px] px-5 pb-10">
        <SectionHeader title="Live Transcript" status={transcriptStatus} />

        {failed ? (
          <div className="mt-3 rounded-paper border-[1.5px] border-mark-out bg-paper-card p-5 shadow-card">
            <Mono className="tracking-data-wide text-mark-out">DEBATE FAILED</Mono>
            <p className="mt-2 text-body text-ink">{failureMessage}</p>
            <p className="mt-2 text-body-sm text-ink-soft">
              Start a new claim, or open a{" "}
              <Link to="/" className="underline hover:text-ink-strong">
                cached demo debate
              </Link>{" "}
              from the landing page — those need no API calls.
            </p>
          </div>
        ) : !transcript.data ? (
          <LockedPanel label="LOADING" reason="fetching the transcript…" />
        ) : args.length === 0 && inProgress ? (
          <CueRow>Debate in progress — waiting for the first argument…</CueRow>
        ) : (
          <>
            <TranscriptView transcript={transcript.data} survivors={survivors} resolved={!!verdict.data} />
            {awaitingNextTurn && <CueRow>{nextAgent} is forming a rebuttal…</CueRow>}
            {inProgress && !awaitingNextTurn && args.length > 0 && (
              <CueRow>Judge is scoring the argument graph…</CueRow>
            )}
          </>
        )}
      </section>

      <ArgumentGraph
        graph={graph.data}
        survivors={survivors}
        resolved={!!verdict.data}
        live={inProgress}
        rounds={transcript.data?.rounds ?? 0}
        texts={new Map(args.map((a) => [a.id, a.text]))}
      />

      <VerdictPanel
        verdict={verdict.data}
        pendingReason={
          failed
            ? "no ruling — the debate did not complete"
            : complete
              ? "the judge is grading the debate…"
              : "the report card is graded after the debate closes"
        }
      >
        <Link to="/" className={primaryButton}>
          New Claim
        </Link>
        <button
          onClick={() => start(claim)}
          disabled={!claim || pending}
          className={secondaryButton}
        >
          {pending ? "Starting…" : "Re-run Debate"}
        </button>
      </VerdictPanel>
    </main>
  );
}

function ClaimStickyBar({
  claim,
  debateId,
  verdict,
  failed,
  inProgress,
  loaded,
  onRestart,
  pending,
}: {
  claim: string;
  debateId: string;
  verdict: Verdict | undefined;
  failed: boolean;
  inProgress: boolean;
  loaded: boolean;
  onRestart: (claim: string) => void;
  pending: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const pass = (verdict?.calibrated_probability ?? 0) >= 0.5;
  const chip = "shrink-0 rounded-[3px] border px-1.5 py-0.5 font-mono text-data tracking-data";

  return (
    <div className="sticky top-0 z-40 border-b-[1.5px] border-ink-strong bg-paper-card shadow-bar">
      <div className="mx-auto flex max-w-shell flex-wrap items-center gap-3.5 px-5 py-2.5">
        <Link to="/" className="font-marker text-brand text-ink-strong">
          Argus
        </Link>
        <Mono className="rounded-[3px] border border-hairline-dashed px-1.5 py-0.5">CLAIM</Mono>
        <div className="flex min-w-0 flex-1 basis-[260px] items-center gap-2">
          <span className="min-w-0 flex-1 truncate text-[15.5px] text-ink-soft">
            {claim || <Mono>debate/{debateId}</Mono>}
          </span>
          <button
            onClick={() => {
              setDraft(claim);
              setEditing(!editing);
            }}
            className="shrink-0 rounded-[3px] border border-dashed border-[#9c9689] px-1.5 py-0.5 font-mono text-[9.5px] tracking-[.1em] text-ink-muted hover:border-ink-strong hover:text-ink-strong"
          >
            EDIT
          </button>
        </div>

        {apiState.usingMock && (
          <span className={cn(chip, "border-dashed border-mark-warn text-[#9a6d17]")}>
            DEMO DATA · BACKEND OFFLINE
          </span>
        )}
        {failed ? (
          <span className={cn(chip, "border-mark-out text-mark-out")}>FAILED</span>
        ) : inProgress ? (
          <span className={cn(chip, "flex items-center gap-1.5 border-mark-out text-mark-out")}>
            <span className="size-1.5 animate-pulse rounded-full bg-mark-out" /> LIVE · POLLING
          </span>
        ) : (
          <span className={cn(chip, "border-hairline-dashed text-ink-muted")}>
            {loaded ? "COMPLETE" : "LOADING"}
          </span>
        )}

        {verdict && (
          <div className="flex shrink-0 items-center gap-3 border-l-[1.5px] border-dashed border-hairline-dashed py-1 pr-2.5 pl-2">
            <span
              className={cn(
                "size-2.5 rounded-full",
                pass
                  ? "bg-mark-in shadow-[0_0_0_2px_#fff,0_0_0_3px_var(--color-mark-in)]"
                  : "bg-mark-out shadow-[0_0_0_2px_#fff,0_0_0_3px_var(--color-mark-out)]",
              )}
            />
            <span className="font-mono text-[17px] font-semibold">
              {Math.round(verdict.calibrated_probability * 100)}%
            </span>
            <span className="font-mono text-[9.5px] leading-[1.35] tracking-[.08em] text-ink-muted">
              SURVIVORS
              <br />
              ADV {verdict.grounded_extension.advocate.length} · SKP{" "}
              {verdict.grounded_extension.skeptic.length}
            </span>
          </div>
        )}
      </div>

      {/* Editing the claim starts a fresh debate — a debate's claim is fixed once it runs. */}
      {editing && (
        <form
          className="mx-auto max-w-shell px-5 pb-3.5"
          onSubmit={(e) => {
            e.preventDefault();
            onRestart(draft);
          }}
        >
          <textarea
            rows={3}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="w-full resize-y rounded-paper border-[1.5px] border-ink-strong bg-[#fffdf6] p-3 font-hand text-[17px] leading-[26px] outline-none"
          />
          <div className="mt-2 flex gap-2">
            <button
              type="submit"
              disabled={!draft.trim() || pending}
              className="rounded-paper bg-ink-strong px-3 py-1.5 font-mono text-data tracking-[.1em] text-paper disabled:opacity-40"
            >
              {pending ? "STARTING…" : "DEBATE THIS CLAIM"}
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="rounded-paper border border-hairline-dashed px-3 py-1.5 font-mono text-data tracking-[.1em] text-ink-muted"
            >
              CANCEL
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function ProgressRail({ status }: { status: Record<Section, Status> }) {
  const [active, setActive] = useState<Section>("claim");

  // Scroll-spy: a section is active once its top crosses 160px.
  useEffect(() => {
    const onScroll = () => {
      let next: Section = "claim";
      for (const id of SECTIONS) {
        const el = document.getElementById(`sec-${id}`);
        if (el && el.getBoundingClientRect().top <= 160) next = id;
      }
      setActive(next);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const jump = (key: Section) => {
    const el = document.getElementById(`sec-${key}`);
    const top = el ? el.getBoundingClientRect().top + window.scrollY - 96 : 0;
    window.scrollTo({ top, behavior: "smooth" });
  };

  const dot: Record<Status, string> = {
    done: "bg-ink-strong border-ink-strong",
    running: "bg-mark-out border-mark-out",
    failed: "bg-transparent border-mark-out",
    pending: "bg-transparent border-ink-ghost",
  };
  const hint: Record<Status, string> = { done: "", running: "live", failed: "failed", pending: "pending" };

  return (
    <nav className="sticky top-(--spacing-rail-offset) z-[35] border-b border-hairline bg-paper-card/95 backdrop-blur-[3px]">
      <div className="mx-auto flex max-w-shell gap-1 overflow-x-auto px-5">
        {SECTIONS.map((key) => (
          <button
            key={key}
            onClick={() => jump(key)}
            className={cn(
              "flex shrink-0 items-center gap-[7px] border-b-2 px-3 pt-2.5 pb-[7px] font-mono text-data font-medium tracking-data",
              active === key ? "border-mark-out text-ink-strong" : "border-transparent text-ink-faint",
            )}
          >
            <span className={cn("size-[7px] rounded-full border", dot[status[key]])} />
            {key.toUpperCase()}
            <span className="text-[8.5px] tracking-[.08em] text-ink-ghost">{hint[status[key]]}</span>
          </button>
        ))}
      </div>
    </nav>
  );
}
