import type { Argument, FactCheck, Transcript } from "@/lib/types";
import { Mono, Stamp, postitStyle } from "./paper";

interface Props {
  transcript: Transcript;
  survivors: Set<string>;
  /** True once the verdict is in — IN/OUT stamps land on every post-it. */
  resolved: boolean;
  /** Per-argument evidence, keyed by argument id. Absent while a debate runs. */
  factChecks?: Record<string, FactCheck> | undefined;
}

/**
 * The evidence behind one argument's score.
 *
 * This is the part of the page that earns the word "auditable": a reader can
 * follow a number back to the Wikipedia sentence it came from and the rule that
 * fired. Abstention is shown just as plainly as a decision — the rules cannot
 * decide most argumentative prose, and hiding that would overstate the system.
 */
function Evidence({ fc }: { fc: FactCheck }) {
  const decided = fc.method === "symbolic";
  const tone = !decided
    ? "text-ink-faint"
    : fc.support_score > 0
      ? "text-mark-in"
      : fc.support_score < 0
        ? "text-mark-out"
        : "text-ink-muted";

  return (
    <div className="mt-3 border-t border-dashed border-ink/20 pt-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <Mono className="tracking-[.12em] text-ink-muted">EVIDENCE</Mono>
        <span className={`font-mono text-data-sm font-semibold ${tone}`}>
          {decided ? `${fc.support_score > 0 ? "+" : ""}${fc.support_score.toFixed(2)}` : "ABSTAINED"}
        </span>
        {fc.rules_fired.length > 0 && (
          <span className="font-mono text-data-sm text-ink-muted">
            {[...new Set(fc.rules_fired)].join(", ").replace(/_/g, " ")}
          </span>
        )}
      </div>

      {fc.triples.length > 0 && (
        <ul className="mt-1.5 mb-0 list-none space-y-0.5 p-0">
          {fc.triples.slice(0, 3).map((t) => (
            <li key={t} className="font-mono text-data-sm text-ink-soft">
              ({t})
            </li>
          ))}
        </ul>
      )}

      {decided && fc.evidence_sentences.length > 0 ? (
        <p className="mt-1.5 mb-0 border-l-2 border-ink/25 pl-2.5 text-[14px] leading-[20px] text-pretty text-ink-soft">
          {fc.evidence_sentences[0]}
        </p>
      ) : (
        !decided && (
          <p className="mt-1.5 mb-0 text-[13.5px] leading-[19px] text-ink-faint">
            No retrieved evidence matched this argument, so the rules abstained
            rather than guessing. It contributes nothing to the verdict.
          </p>
        )
      )}
    </div>
  );
}

function PostIt({
  arg,
  resolved,
  survived,
  factCheck,
}: {
  arg: Argument;
  resolved: boolean;
  survived: boolean;
  factCheck?: FactCheck | undefined;
}) {
  const advocate = arg.agent === "advocate";
  return (
    <div
      style={postitStyle(arg.agent, arg.round)}
      className="postit-sheen animate-slide-in relative min-w-0 rounded-postit px-4.5 pt-4 pb-4 shadow-postit"
    >
      <div className="mb-2.5 flex flex-wrap items-center gap-2">
        <span className="rounded-paper bg-ink/90 px-1.5 py-0.5 font-mono text-data-sm font-semibold tracking-[.12em] text-[#fffdf6]">
          {arg.id}
        </span>
        <span className="rounded-paper border border-ink/30 px-1.5 py-0.5 font-mono text-data-sm tracking-[.1em] text-ink-soft">
          CONF {arg.self_confidence.toFixed(2)}
        </span>
        {arg.attacks.length > 0 && (
          <span className="font-mono text-data-sm text-ink-muted">
            attacks → {arg.attacks.join(", ")}
          </span>
        )}
      </div>
      <p className="m-0 pr-14 text-body text-pretty text-ink">{arg.text}</p>
      {factCheck && <Evidence fc={factCheck} />}
      {resolved && (
        <Stamp
          tone={survived ? "in" : "out"}
          rotate={advocate ? -7 : 6}
          className="absolute right-2.5 bottom-2"
        >
          {survived ? "IN" : "OUT"}
        </Stamp>
      )}
    </div>
  );
}

function AgentBadge({ agent }: { agent: Argument["agent"] }) {
  const advocate = agent === "advocate";
  return (
    <div className="flex items-center gap-2">
      <span
        className={`grid size-5 place-items-center border-[1.5px] border-ink-strong bg-white font-mono text-[9.5px] font-semibold ${advocate ? "rounded-full" : "rotate-45"}`}
      >
        <span className={advocate ? "" : "-rotate-45"}>{advocate ? "A" : "S"}</span>
      </span>
      <Mono className="tracking-[.16em] text-[#5c574e]">{advocate ? "ADVOCATE" : "SKEPTIC"}</Mono>
    </div>
  );
}

export function TranscriptView({ transcript, survivors, resolved, factChecks }: Props) {
  const rounds = [...new Set(transcript.arguments.map((a) => a.round))].sort((a, b) => a - b);

  return (
    <>
      {rounds.map((round) => (
        <div key={round} className="mt-7">
          <div className="mb-4.5 flex items-center gap-2.5">
            <span className="rounded-paper border border-hairline-dashed bg-chip-bg px-2 py-[3px] font-mono text-data font-semibold tracking-[.2em] text-ink-muted">
              ROUND {round}
            </span>
            <span className="h-0 flex-1 border-b border-hairline" />
          </div>
          {/* Advocate left, Skeptic right — stacks at phone widths */}
          <div className="grid grid-cols-[repeat(auto-fit,minmax(290px,1fr))] items-start gap-6">
            {(["advocate", "skeptic"] as const).map((agent) => (
              <div key={agent} className="flex min-w-0 flex-col gap-6">
                <AgentBadge agent={agent} />
                {transcript.arguments
                  .filter((a) => a.round === round && a.agent === agent)
                  .map((a) => (
                    <PostIt
                      key={a.id}
                      arg={a}
                      resolved={resolved}
                      survived={survivors.has(a.id)}
                      factCheck={factChecks?.[a.id]}
                    />
                  ))}
              </div>
            ))}
          </div>
        </div>
      ))}
    </>
  );
}
