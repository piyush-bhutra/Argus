import type { ReactNode } from "react";
import type { Verdict } from "@/lib/types";
import { cn } from "@/lib/utils";
import { LockedPanel, Mono, SectionHeader, Stamp } from "./paper";

interface Props {
  verdict: Verdict | undefined;
  /** Shown in the locked panel while there is no verdict yet. */
  pendingReason?: string;
  /** Action buttons rendered under the report card. */
  children?: ReactNode;
}

function Gauge({ p }: { p: number }) {
  const R = 96;
  const cx = 116;
  const cy = 112;
  const point = (frac: number) => {
    const a = Math.PI * (1 - frac);
    return [cx + R * Math.cos(a), cy - R * Math.sin(a)] as const;
  };
  const arc = (from: number, to: number) => {
    const [x1, y1] = point(from);
    const [x2, y2] = point(to);
    return `M ${x1} ${y1} A ${R} ${R} 0 0 1 ${x2} ${y2}`;
  };
  const ang = Math.PI * (1 - Math.max(0, Math.min(1, p)));
  return (
    <svg
      width={232}
      height={126}
      className="mt-1.5 block"
      role="img"
      aria-label={`Gauge at ${Math.round(p * 100)}%`}
    >
      <path d={arc(0, 0.34)} fill="none" stroke="var(--color-mark-out)" strokeWidth={13} />
      <path d={arc(0.34, 0.66)} fill="none" stroke="var(--color-mark-warn)" strokeWidth={13} />
      <path d={arc(0.66, 1)} fill="none" stroke="var(--color-mark-in)" strokeWidth={13} />
      <line
        x1={cx}
        y1={cy}
        x2={cx + (R - 20) * Math.cos(ang)}
        y2={cy - (R - 20) * Math.sin(ang)}
        stroke="var(--color-ink)"
        strokeWidth={3}
        strokeLinecap="round"
      />
      <circle cx={cx} cy={cy} r={6} fill="var(--color-ink)" />
      <text x={12} y={124} className="font-mono" fontSize={10} fill="var(--color-ink-faint)">
        FALSE
      </text>
      <text x={186} y={124} className="font-mono" fontSize={10} fill="var(--color-ink-faint)">
        TRUE
      </text>
    </svg>
  );
}

function SurvivorChips({ label, ids }: { label: string; ids: string[] }) {
  return (
    <>
      <Mono className="tracking-[.12em] text-ink-muted">{label}</Mono>
      {ids.length ? (
        ids.map((id) => (
          <span
            key={id}
            className="rounded-paper border border-mark-in bg-survivor-chip-bg px-2 py-0.5 font-mono text-data font-semibold text-survivor-chip-ink"
          >
            {id}
          </span>
        ))
      ) : (
        <span className="rounded-paper border border-dashed border-locked-border px-2 py-0.5 font-mono text-data text-ink-faint">
          none
        </span>
      )}
    </>
  );
}

/**
 * The three signals the judge combined, graded like subjects on a report card.
 *
 * This is the diegetic centre of the design: "grading a claim" is literally what
 * the judge computes, and these are the marks that roll up into the final score.
 * Each signal is bounded in [-1, 1], positive favouring the claim, so the bars
 * are directly comparable — a reader can see at a glance whether a verdict came
 * from the argument graph, from the evidence, or merely from how confident the
 * agents sounded.
 *
 * The weighted contributions are shown because they sum, through a sigmoid, to
 * exactly the probability above — so the arithmetic on screen can be checked
 * rather than taken on trust.
 */
const SUBJECTS = [
  {
    key: "structural",
    label: "STRUCTURE",
    gloss: "which arguments survived the attack graph, weighted by their evidence",
  },
  {
    key: "factcheck",
    label: "EVIDENCE",
    gloss: "retrieved evidence for each side, judged by the symbolic rules",
  },
  {
    key: "confidence",
    label: "CONVICTION",
    gloss: "how confident each agent claimed to be — the weakest signal, weighted lowest",
  },
] as const;

function SignalBar({ value }: { value: number }) {
  // Centre-anchored: the bar grows left for the skeptic, right for the advocate,
  // because these are signed deltas rather than magnitudes.
  const pct = Math.min(1, Math.abs(value)) * 50;
  const positive = value >= 0;
  return (
    <div className="relative mt-1.5 h-2.5 w-full rounded-paper border border-hairline bg-chip-bg">
      <span className="absolute inset-y-0 left-1/2 w-px bg-ink-ghost" aria-hidden />
      <span
        className={cn("absolute inset-y-px rounded-paper", positive ? "bg-mark-in" : "bg-mark-out")}
        style={positive ? { left: "50%", width: `${pct}%` } : { right: "50%", width: `${pct}%` }}
      />
    </div>
  );
}

function GradedSignals({ verdict: v }: { verdict: Verdict }) {
  const signals = v.signals;
  if (!signals) return null;
  const weights = v.signal_weights ?? { structural: 1, factcheck: 1, confidence: 0.5 };

  return (
    <div className="mt-5 border-t border-hairline pt-4">
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Mono className="tracking-data-wide">GRADED SIGNALS</Mono>
        <span className="font-mono text-data-sm text-ink-faint">
          each −1…+1 · negative favours FALSE · weighted, they sum to the score above
        </span>
      </div>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-x-6 gap-y-4">
        {SUBJECTS.map(({ key, label, gloss }) => {
          const value = signals[key] ?? 0;
          const weighted = value * (weights[key] ?? 0);
          return (
            <div key={key} className="min-w-0">
              <div className="flex items-baseline justify-between gap-2">
                <Mono className="tracking-[.12em] text-ink-muted">{label}</Mono>
                <span
                  className={cn(
                    "font-mono text-data font-semibold",
                    value > 0 ? "text-mark-in" : value < 0 ? "text-mark-out" : "text-ink-faint",
                  )}
                >
                  {value > 0 ? "+" : ""}
                  {value.toFixed(2)}
                </span>
              </div>
              <SignalBar value={value} />
              <div className="mt-1.5 font-mono text-data-sm text-ink-faint">
                × {(weights[key] ?? 0).toFixed(2)} = {weighted > 0 ? "+" : ""}
                {weighted.toFixed(2)}
              </div>
              <p className="mt-1 mb-0 text-[13.5px] leading-[18px] text-pretty text-ink-faint">
                {gloss}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * How much of the verdict the symbolic rules could actually account for, and
 * which asserted attacks were refused.
 *
 * Both numbers are deliberately prominent rather than tucked away. Coverage is
 * usually well under half — the rules cannot decide argumentative prose — and a
 * system that reports an auditable probability while hiding how much of it was
 * audited would be overstating itself.
 */
function EvidenceAudit({ verdict: v }: { verdict: Verdict }) {
  const coverage = v.symbolic_coverage;
  const dropped = v.dropped_edges ?? [];
  if (coverage == null && dropped.length === 0) return null;

  return (
    <div className="mt-4 border-t border-hairline pt-3.5">
      <div className="mb-2">
        <Mono className="tracking-data-wide">EVIDENCE AUDIT</Mono>
      </div>

      {coverage != null && (
        <div className="flex flex-wrap items-baseline gap-2 font-mono text-data text-ink-muted">
          <span className="font-semibold text-ink-strong">{Math.round(coverage * 100)}%</span>
          <span>of arguments decided by the symbolic rules</span>
          {coverage < 1 && (
            <span className="text-ink-faint">— the rest abstained and contributed nothing</span>
          )}
        </div>
      )}

      {dropped.length > 0 && (
        <div className="mt-2.5">
          <div className="mb-1.5 font-mono text-data text-ink-muted">
            {dropped.length} asserted attack{dropped.length === 1 ? "" : "s"} refused — no evidence
            backed the attacker, so {dropped.length === 1 ? "it" : "they"} never entered the graph:
          </div>
          <div className="flex flex-wrap gap-[7px]">
            {dropped.map(([source, target]) => (
              <span
                key={`${source}->${target}`}
                className="rounded-paper border border-dashed border-mark-out px-2 py-0.5 font-mono text-data text-mark-out line-through"
              >
                {source} → {target}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function VerdictPanel({
  verdict,
  pendingReason = "the report card is graded after the debate closes",
  children,
}: Props) {
  return (
    <section id="sec-ruling" className="mx-auto max-w-shell scroll-mt-[120px] px-5 pb-[90px]">
      <SectionHeader title="Ruling" status={verdict ? "GRADED" : "PENDING"} />
      {!verdict ? <LockedPanel reason={pendingReason} /> : <RulingCard verdict={verdict} />}
      {children && <div className="mt-5 flex flex-wrap gap-3">{children}</div>}
    </section>
  );
}

function RulingCard({ verdict: v }: { verdict: Verdict }) {
  const pct = Math.round(v.calibrated_probability * 100);
  const pass = v.calibrated_probability >= 0.5;
  const delta = v.calibrated_probability - v.raw_probability;

  return (
    <div className="relative mt-3 rounded-paper border-[1.5px] border-ink-strong bg-paper-card px-7 pt-6 pb-7 shadow-card-lg">
      <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] items-start gap-[30px]">
        <div className="min-w-0">
          <Mono className="tracking-data-wide">CALIBRATED P(TRUE)</Mono>
          <Gauge p={v.calibrated_probability} />
          <div className="flex items-baseline gap-2.5">
            <span
              className={cn("font-marker text-display", pass ? "text-mark-in" : "text-mark-out")}
            >
              {pct}%
            </span>
            <span className="text-[17px] leading-[23px] text-ink-soft">
              likely
              <br />
              {pass ? "true" : "false"}
            </span>
            {/* PASS/FAIL sits beside the number, never over it */}
            <Stamp
              tone={pass ? "in" : "out"}
              rotate={-8}
              size="text-stamp-xl"
              double
              className="ml-1.5"
            >
              {pass ? "PASS" : "FAIL"}
            </Stamp>
          </div>
          <div className="mt-3 flex flex-wrap gap-4.5 font-mono text-data tracking-[.08em] text-ink-muted">
            <span>RAW {v.raw_probability.toFixed(2)}</span>
            <span>CALIBRATED {v.calibrated_probability.toFixed(2)}</span>
            <span className={delta < 0 ? "text-mark-out" : undefined}>
              Δ {delta >= 0 ? "+" : "−"}
              {Math.abs(delta).toFixed(2)}
            </span>
          </div>
          <div className="mt-3.5 mb-2">
            <Mono className="tracking-data-wide">GROUNDED-EXTENSION SURVIVORS</Mono>
          </div>
          <div className="flex flex-wrap items-center gap-[7px]">
            <SurvivorChips label="ADV" ids={v.grounded_extension.advocate} />
            <span className="h-4 w-px bg-hairline" />
            <SurvivorChips label="SKP" ids={v.grounded_extension.skeptic} />
          </div>
        </div>

        <div className="min-w-0">
          <div className="mb-2">
            <Mono className="tracking-data-wide">JUDGE'S NOTE</Mono>
          </div>
          <p className="m-0 text-[18px] leading-[27px] text-pretty text-ink-strong">
            {v.explanation}
          </p>
          <GradedSignals verdict={v} />
          <EvidenceAudit verdict={v} />
        </div>
      </div>
    </div>
  );
}
