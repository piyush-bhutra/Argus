import type { Verdict } from "@/lib/types";
import { cn } from "@/lib/utils";

function Gauge({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(1, value));
  const r = 62;
  const c = Math.PI * r; // semicircle length
  return (
    <div className="relative w-full max-w-[220px]">
      <svg viewBox="0 0 160 92" className="w-full">
        <path
          d="M 18 82 A 62 62 0 0 1 142 82"
          fill="none"
          stroke="var(--muted)"
          strokeWidth="12"
          strokeLinecap="round"
        />
        <path
          d="M 18 82 A 62 62 0 0 1 142 82"
          fill="none"
          stroke={pct >= 0.5 ? "var(--survived)" : "var(--skeptic)"}
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={`${c * pct} ${c}`}
        />
      </svg>
      <div className="absolute inset-x-0 bottom-0 text-center">
        <div className="font-mono text-4xl font-semibold tabular-nums">
          {(pct * 100).toFixed(0)}
          <span className="text-xl text-muted-foreground">%</span>
        </div>
      </div>
    </div>
  );
}

export function VerdictPanel({ verdict }: { verdict: Verdict }) {
  const { advocate, skeptic } = verdict.grounded_extension;
  return (
    <div className="space-y-6">
      <div className="flex flex-col items-center gap-4 rounded-lg border border-border bg-card p-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col items-center gap-1">
          <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            Calibrated probability
          </span>
          <Gauge value={verdict.calibrated_probability} />
        </div>
        <div className="grid gap-4 text-center sm:text-right">
          <div>
            <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              Raw probability
            </div>
            <div className="font-mono text-xl tabular-nums text-foreground/80">
              {(verdict.raw_probability * 100).toFixed(1)}%
            </div>
          </div>
          <div>
            <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              Calibration delta
            </div>
            <div
              className={cn(
                "font-mono text-xl tabular-nums",
                verdict.calibrated_probability >= verdict.raw_probability
                  ? "text-survived"
                  : "text-skeptic",
              )}
            >
              {verdict.calibrated_probability >= verdict.raw_probability ? "+" : ""}
              {((verdict.calibrated_probability - verdict.raw_probability) * 100).toFixed(1)} pts
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-advocate/25 bg-card p-4">
          <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-advocate">
            Grounded · advocate
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {advocate.length ? (
              advocate.map((id) => (
                <span
                  key={id}
                  className="rounded bg-advocate-soft px-1.5 py-0.5 font-mono text-[11px] text-advocate"
                >
                  {id}
                </span>
              ))
            ) : (
              <span className="text-xs text-muted-foreground">none survived</span>
            )}
          </div>
        </div>
        <div className="rounded-lg border border-skeptic/25 bg-card p-4">
          <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-skeptic">
            Grounded · skeptic
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {skeptic.length ? (
              skeptic.map((id) => (
                <span
                  key={id}
                  className="rounded bg-skeptic-soft px-1.5 py-0.5 font-mono text-[11px] text-skeptic"
                >
                  {id}
                </span>
              ))
            ) : (
              <span className="text-xs text-muted-foreground">none survived</span>
            )}
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card p-4">
        <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
          Explanation
        </div>
        <p className="mt-2 text-sm leading-relaxed text-foreground/90">{verdict.explanation}</p>
      </div>
    </div>
  );
}
