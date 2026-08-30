import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ArrowLeft, Loader2, Radio } from "lucide-react";
import { apiState, getGraph, getTranscript, getVerdict } from "@/lib/api";
import { TranscriptView } from "@/components/debate/TranscriptView";
import { ArgumentGraph } from "@/components/debate/ArgumentGraph";
import { VerdictPanel } from "@/components/debate/VerdictPanel";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/debate/$debateId")({
  head: () => ({
    meta: [
      { title: "Debate transcript — Dialectic" },
      {
        name: "description",
        content:
          "Live advocate-vs-skeptic transcript, argument attack graph, and calibrated verdict for a single claim.",
      },
      { property: "og:title", content: "Debate transcript — Dialectic" },
      {
        property: "og:description",
        content: "Transcript, attack graph, and calibrated verdict for a verified claim.",
      },
    ],
  }),
  component: DebateView,
});

type Tab = "transcript" | "graph" | "verdict";

function DebateView() {
  const { debateId } = Route.useParams();
  const [tab, setTab] = useState<Tab>("transcript");
  const [selected, setSelected] = useState<string | null>(null);

  const transcript = useQuery({
    queryKey: ["transcript", debateId],
    queryFn: () => getTranscript(debateId),
    refetchInterval: (q) => (q.state.data?.status === "in_progress" ? 3000 : false),
  });

  const graph = useQuery({ queryKey: ["graph", debateId], queryFn: () => getGraph(debateId) });
  const verdict = useQuery({
    queryKey: ["verdict", debateId],
    queryFn: () => getVerdict(debateId),
    enabled: transcript.data?.status === "complete",
  });

  const survivors = new Set([
    ...(verdict.data?.grounded_extension.advocate ?? []),
    ...(verdict.data?.grounded_extension.skeptic ?? []),
  ]);

  const inProgress = transcript.data?.status === "in_progress";

  return (
    <main className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-6 py-3">
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 font-mono text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-3.5" /> new claim
          </Link>
          <span className="font-mono text-xs text-muted-foreground">debate/{debateId}</span>
          {apiState.usingMock && (
            <span className="rounded border border-skeptic/50 px-2 py-1 font-mono text-[11px] text-skeptic">
              demo data · backend offline
            </span>
          )}
          <div className="ml-auto flex items-center gap-3">
            {inProgress ? (
              <span className="inline-flex items-center gap-1.5 rounded border border-primary/40 px-2 py-1 font-mono text-[11px] text-primary">
                <Radio className="size-3 animate-pulse" /> live · polling
              </span>
            ) : (
              <span className="rounded border border-border px-2 py-1 font-mono text-[11px] text-muted-foreground">
                complete
              </span>
            )}
          </div>
        </div>
        <div className="mx-auto flex max-w-6xl gap-1 px-6">
          {(["transcript", "graph", "verdict"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "-mb-px border-b-2 px-3 py-2 font-mono text-xs uppercase tracking-[0.14em] transition-colors",
                tab === t
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {t}
            </button>
          ))}
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-6 py-8">
        {verdict.data && (
          <p className="mb-6 border-l-2 border-primary pl-3 text-sm text-muted-foreground">
            <span className="font-mono text-[11px] uppercase tracking-[0.18em]">Claim</span>
            <br />
            <span className="text-foreground">{verdict.data.claim}</span>
          </p>
        )}

        {tab === "transcript" &&
          (transcript.isLoading || !transcript.data ? (
            <Loading />
          ) : (
            <TranscriptView
              transcript={transcript.data}
              survivors={survivors}
              highlightId={selected}
              onSelect={setSelected}
            />
          ))}

        {tab === "graph" &&
          (graph.isLoading || !graph.data ? (
            <Loading />
          ) : (
            <div className="space-y-4">
              <ArgumentGraph
                graph={graph.data}
                survivors={survivors}
                selectedId={selected}
                onSelect={setSelected}
              />
              <div className="flex flex-wrap gap-4 font-mono text-[11px] text-muted-foreground">
                <span className="inline-flex items-center gap-2">
                  <span className="size-3 rounded-full border border-advocate bg-advocate/20" /> advocate
                </span>
                <span className="inline-flex items-center gap-2">
                  <span className="size-3 rounded-[2px] border border-skeptic bg-skeptic/20" /> skeptic
                </span>
                <span className="inline-flex items-center gap-2">
                  <span className="size-3 rounded-full border border-dashed border-survived" /> survived
                </span>
                <span>arrow = attacks</span>
              </div>
            </div>
          ))}

        {tab === "verdict" &&
          (verdict.data ? (
            <VerdictPanel verdict={verdict.data} />
          ) : (
            <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
              {inProgress ? "Verdict is computed once the debate completes." : <Loading />}
            </div>
          ))}
      </div>
    </main>
  );
}

function Loading() {
  return (
    <div className="flex items-center gap-2 py-16 text-sm text-muted-foreground">
      <Loader2 className="size-4 animate-spin" /> Loading…
    </div>
  );
}
