import { useEffect, useRef, useState } from "react";
import type { DebateGraph, GraphNode } from "@/lib/types";
import { LockedPanel, Mono, SectionHeader, Stamp, postitStyle } from "./paper";

interface Props {
  graph: DebateGraph | undefined;
  survivors: Set<string>;
  /** Verdict is in: stamps land, defeated nodes cross out, survivors glow. */
  resolved: boolean;
  /** Debate still streaming — graph grows as nodes arrive. */
  live: boolean;
  /** Planned round count, so future columns are drawn before their nodes arrive. */
  rounds: number;
  /** Argument text by id (from the transcript) for the node gist. */
  texts: Map<string, string>;
}

// Deterministic layout: one column per round, Advocate row on top.
// ponytail: one node per agent per round (what the orchestrator emits); stack cells if that changes.
const COL = 233;
const NODE_W = 206;
const NODE_H = 104;
const HEIGHT = 392;
const colX = (round: number) => 13 + (round - 1) * COL;
const rowY = (agent: GraphNode["agent"]) => (agent === "advocate" ? 40 : 214);

const STEP_MS = 620; // one reveal step per debate round

/** Replay: hides everything, reveals one round per step, then re-applies the marks. */
function useReplay(cols: number) {
  const [stage, setStage] = useState(Infinity); // highest round revealed
  const [marksOn, setMarksOn] = useState(true);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const clear = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };
  useEffect(() => clear, []);

  function replay() {
    clear();
    setStage(0);
    setMarksOn(false);
    for (let r = 1; r <= cols; r++) {
      timers.current.push(setTimeout(() => setStage(r), 260 + (r - 1) * STEP_MS));
    }
    timers.current.push(
      setTimeout(() => {
        setStage(Infinity);
        setMarksOn(true);
      }, 260 + (cols - 1) * STEP_MS + 740),
    );
  }

  return { stage, marksOn, replay };
}

function Node({
  node,
  text,
  visible,
  marked,
  survives,
}: {
  node: GraphNode;
  text: string | undefined;
  visible: boolean;
  marked: boolean;
  survives: boolean;
}) {
  const crossed = marked && !survives;
  const advocate = node.agent === "advocate";
  return (
    <div
      title={text}
      style={{
        ...postitStyle(node.agent, node.round),
        left: colX(node.round),
        top: rowY(node.agent),
        width: NODE_W,
        height: NODE_H,
        opacity: visible ? 1 : 0,
        filter: crossed ? "grayscale(1) opacity(.6)" : "none",
        // Swapping the animation restarts it — that's what makes replay work without remounting.
        animation: !visible ? "none" : marked && survives ? "var(--animate-glow)" : "var(--animate-pop-in)",
      }}
      className="postit-sheen absolute z-[3] rounded-postit px-3 pt-2.5 pb-2.5 shadow-postit-sm transition-[opacity,filter] duration-(--duration-fade)"
    >
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="truncate font-mono text-[9.5px] font-semibold tracking-[.14em] text-ink">
          {node.label ?? node.id} · {advocate ? "ADVOCATE" : "SKEPTIC"}
        </span>
        <span className="rounded-paper border border-ink/35 px-1.5 py-px font-mono text-[8.5px] tracking-[.1em] text-ink-soft">
          R{node.round}
        </span>
      </div>
      <div className="line-clamp-3 text-body-sm text-pretty text-[#3a3732]">{text}</div>

      {marked && (
        <Stamp
          tone={survives ? "in" : "out"}
          rotate={advocate ? -6 : 5}
          size="text-stamp-sm"
          className="absolute -right-2 -bottom-2.5 bg-paper"
        >
          {survives ? "IN" : "OUT"}
        </Stamp>
      )}
      {/* red X — reserved for the graph section only */}
      {crossed && (
        <span className="pointer-events-none absolute inset-0">
          <span className="absolute inset-x-[4%] top-1/2 h-[2.5px] rotate-[9deg] bg-mark-out" />
          <span className="absolute inset-x-[4%] top-1/2 h-[2.5px] -rotate-[9deg] bg-mark-out" />
        </span>
      )}
    </div>
  );
}

export function ArgumentGraph({ graph, survivors, resolved, live, rounds, texts }: Props) {
  const nodes = graph?.nodes ?? [];
  const cols = Math.max(rounds, ...nodes.map((n) => n.round), 1);
  const width = cols * COL + 1;
  const { stage, marksOn, replay } = useReplay(cols);
  const marked = resolved && marksOn;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const inCount = nodes.filter((n) => survivors.has(n.id)).length;

  const status = resolved
    ? `GROUNDED EXTENSION · ${inCount} IN / ${nodes.length - inCount} OUT`
    : live && nodes.length
      ? "GROWING · LIVE"
      : "PENDING";

  return (
    <section id="sec-graph" className="mx-auto max-w-shell scroll-mt-[120px] px-5 pb-2">
      <SectionHeader title="Argument Graph" status={status}>
        {resolved && nodes.length > 0 && (
          <button
            onClick={replay}
            className="rounded-paper border-[1.5px] border-ink-strong px-2.5 py-1 font-mono text-data tracking-[.12em] text-ink-strong hover:bg-ink-strong hover:text-paper"
          >
            ↻ REPLAY
          </button>
        )}
      </SectionHeader>

      {nodes.length === 0 ? (
        <LockedPanel reason="the attack map draws itself as arguments arrive" />
      ) : (
        <div className="mt-2.5 flex flex-col gap-4.5">
          <div className="overflow-x-auto rounded-paper border-[1.5px] border-ink-strong bg-paper-card p-4.5 shadow-card">
            <div
              className="relative mx-auto"
              style={{ width, height: HEIGHT }}
              role="img"
              aria-label="Argument attack graph"
            >
              <div
                className="absolute inset-0 z-[1] grid"
                style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}
              >
                {Array.from({ length: cols }, (_, i) => (
                  <div key={i} className="flex justify-center border-l border-dashed border-[#ded8ca] pt-0.5">
                    <Mono className="tracking-[.16em] text-ink-ghost">ROUND {i + 1}</Mono>
                  </div>
                ))}
              </div>

              <svg
                width={width}
                height={HEIGHT}
                className="pointer-events-none absolute inset-0 z-[2] overflow-visible"
              >
                <defs>
                  <marker
                    id="argus-arrow"
                    viewBox="0 0 10 10"
                    refX="8"
                    refY="5"
                    markerWidth="7"
                    markerHeight="7"
                    orient="auto-start-reverse"
                  >
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--color-ink-muted)" />
                  </marker>
                </defs>
                {graph?.edges.map((e) => {
                  const a = byId.get(e.source);
                  const b = byId.get(e.target);
                  if (!a || !b) return null;
                  // Edges leave/enter on the side facing the other row.
                  const x1 = colX(a.round) + NODE_W / 2;
                  const x2 = colX(b.round) + NODE_W / 2;
                  const y1 = rowY(a.agent) + (a.agent === "advocate" ? NODE_H : 0);
                  const y2 = rowY(b.agent) + (b.agent === "advocate" ? NODE_H + 2 : -4);
                  const sameRow = a.agent === b.agent;
                  const mx = (x1 + x2) / 2 + (x1 === x2 ? 34 : 0);
                  const my = (y1 + y2) / 2 + (sameRow ? (a.agent === "advocate" ? 40 : -40) : 0);
                  const shown = Math.max(a.round, b.round) <= stage;
                  const dim = marked && !survivors.has(b.id); // edges into defeated nodes collapse
                  return (
                    <path
                      key={`${e.source}-${e.target}`}
                      d={`M ${x1} ${y1} Q ${mx} ${my} ${x2} ${y2}`}
                      fill="none"
                      stroke={dim ? "#bdb7aa" : "var(--color-ink-muted)"}
                      strokeWidth={1.8}
                      strokeDasharray="7 5"
                      strokeLinecap="round"
                      markerEnd="url(#argus-arrow)"
                      style={{
                        opacity: shown ? (dim ? 0.45 : 1) : 0,
                        transition: "opacity var(--duration-fade) ease, stroke var(--duration-fade) ease",
                      }}
                    />
                  );
                })}
              </svg>

              {nodes.map((n) => (
                <Node
                  key={n.id}
                  node={n}
                  text={texts.get(n.id)}
                  visible={n.round <= stage}
                  marked={marked}
                  survives={survivors.has(n.id)}
                />
              ))}
            </div>
          </div>

          <div className="grid grid-cols-[repeat(auto-fit,minmax(270px,1fr))] items-start gap-4">
            <div className="rounded-paper border-[1.5px] border-ink-strong bg-white p-3.5 shadow-card-sm">
              <Mono className="tracking-[.16em]">LEGEND</Mono>
              <div className="mt-2.5 flex flex-col gap-2.5 text-body-sm text-[#3a3732]">
                <div className="flex items-center gap-2">
                  <span className="size-4 rounded-paper bg-mark-in" />
                  survives — in the grounded extension
                </div>
                <div className="flex items-center gap-2">
                  <span className="size-4 rounded-paper bg-mark-out" />
                  defeated — crossed out, greyed
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-6.5 border-t-2 border-dashed border-ink-muted" />
                  attack direction
                </div>
              </div>
            </div>
            <div className="postit-sheen rotate-[1.2deg] bg-postit-note p-3.5 shadow-postit-sm">
              <Mono className="tracking-[.16em] text-ink-muted">FIXPOINT</Mono>
              <div className="mt-2 text-[16px] leading-[23px] text-pretty text-[#3a3732]">
                Unattacked arguments are accepted, everything they attack is rejected, and the rest
                is recomputed until nothing changes.
              </div>
              {resolved && (
                <div className="mt-2.5 font-mono text-[11px] text-ink">
                  IN {`{${nodes.filter((n) => survivors.has(n.id)).map((n) => n.label ?? n.id).join(", ")}}`} · OUT{" "}
                  {`{${nodes.filter((n) => !survivors.has(n.id)).map((n) => n.label ?? n.id).join(", ")}}`}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
