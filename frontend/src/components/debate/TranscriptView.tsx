import { ShieldCheck, Swords } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Argument, Transcript } from "@/lib/types";

interface Props {
  transcript: Transcript;
  survivors: Set<string>;
  highlightId?: string | null | undefined;
  onSelect?: ((id: string) => void) | undefined;
}

function ConfidenceBadge({ value }: { value: number }) {
  return (
    <span className="rounded border border-border bg-surface-raised px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
      conf {value.toFixed(2)}
    </span>
  );
}

function ArgumentCard({
  arg,
  survived,
  highlighted,
  onSelect,
}: {
  arg: Argument;
  survived: boolean;
  highlighted: boolean;
  onSelect?: ((id: string) => void) | undefined;
}) {
  const isAdvocate = arg.agent === "advocate";
  return (
    <button
      type="button"
      onClick={() => onSelect?.(arg.id)}
      className={cn(
        "w-full rounded-lg border bg-card p-4 text-left transition-colors",
        isAdvocate ? "border-advocate/25 hover:border-advocate/60" : "border-skeptic/25 hover:border-skeptic/60",
        highlighted && "ring-1 ring-ring",
      )}
    >
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 font-mono text-[11px] uppercase tracking-wide",
            isAdvocate ? "bg-advocate-soft text-advocate" : "bg-skeptic-soft text-skeptic",
          )}
        >
          {isAdvocate ? <ShieldCheck className="size-3" /> : <Swords className="size-3" />}
          {arg.agent}
        </span>
        <span className="font-mono text-[11px] text-muted-foreground">#{arg.id}</span>
        <ConfidenceBadge value={arg.self_confidence} />
        {survived && (
          <span className="rounded border border-survived/40 px-1.5 py-0.5 font-mono text-[11px] text-survived">
            survived
          </span>
        )}
      </div>
      <p className="text-sm leading-relaxed text-foreground/90">{arg.text}</p>
      {arg.attacks.length > 0 && (
        <p className="mt-2 font-mono text-[11px] text-muted-foreground">
          attacks → {arg.attacks.join(", ")}
        </p>
      )}
    </button>
  );
}

export function TranscriptView({ transcript, survivors, highlightId, onSelect }: Props) {
  const rounds = [...new Set(transcript.arguments.map((a) => a.round))].sort((a, b) => a - b);

  return (
    <div className="space-y-8">
      {rounds.map((round) => {
        const args = transcript.arguments.filter((a) => a.round === round);
        return (
          <section key={round}>
            <div className="mb-3 flex items-center gap-3">
              <span className="font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground">
                Round {round}
              </span>
              <span className="h-px flex-1 bg-border" />
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-4">
                {args
                  .filter((a) => a.agent === "advocate")
                  .map((a) => (
                    <ArgumentCard
                      key={a.id}
                      arg={a}
                      survived={survivors.has(a.id)}
                      highlighted={highlightId === a.id}
                      onSelect={onSelect}
                    />
                  ))}
              </div>
              <div className="space-y-4">
                {args
                  .filter((a) => a.agent === "skeptic")
                  .map((a) => (
                    <ArgumentCard
                      key={a.id}
                      arg={a}
                      survived={survivors.has(a.id)}
                      highlighted={highlightId === a.id}
                      onSelect={onSelect}
                    />
                  ))}
              </div>
            </div>
          </section>
        );
      })}
    </div>
  );
}
