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
    <svg width={232} height={126} className="mt-1.5 block" role="img" aria-label={`Gauge at ${Math.round(p * 100)}%`}>
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

export function VerdictPanel({
  verdict,
  pendingReason = "the report card is graded after the debate closes",
  children,
}: Props) {
  return (
    <section id="sec-ruling" className="mx-auto max-w-shell scroll-mt-[120px] px-5 pb-[90px]">
      <SectionHeader title="Ruling" status={verdict ? "GRADED" : "PENDING"} />
      {!verdict ? (
        <LockedPanel reason={pendingReason} />
      ) : (
        <RulingCard verdict={verdict} />
      )}
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
            <span className={cn("font-marker text-display", pass ? "text-mark-in" : "text-mark-out")}>
              {pct}%
            </span>
            <span className="text-[17px] leading-[23px] text-ink-soft">
              likely
              <br />
              {pass ? "true" : "false"}
            </span>
            {/* PASS/FAIL sits beside the number, never over it */}
            <Stamp tone={pass ? "in" : "out"} rotate={-8} size="text-stamp-xl" double className="ml-1.5">
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
          <p className="m-0 text-[18px] leading-[27px] text-pretty text-ink-strong">{v.explanation}</p>
        </div>
      </div>
    </div>
  );
}
