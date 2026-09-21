import { useNavigate } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";
import { startDebate } from "@/lib/api";
import type { AgentRole } from "@/lib/types";
import { cn } from "@/lib/utils";

/* Shared notebook-paper primitives used by both routes and the debate components. */

export function Mono({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <span className={cn("font-mono text-data tracking-data text-ink-faint", className)}>
      {children}
    </span>
  );
}

/** Rubber stamp. "fail" = double border (PASS/FAIL on the ruling). */
export function Stamp({
  children,
  tone,
  rotate,
  size = "text-stamp",
  double = false,
  className,
}: {
  children: ReactNode;
  tone: "in" | "out";
  rotate: number;
  size?: string;
  double?: boolean;
  className?: string;
}) {
  return (
    <span
      style={{ transform: `rotate(${rotate}deg)` }}
      className={cn(
        "animate-stamp inline-block rounded-[3px] px-2.5 pb-0.5 font-marker opacity-90",
        size,
        tone === "in" ? "border-mark-in text-mark-in" : "border-mark-out text-mark-out",
        double ? "border-4 border-double" : "border-[3px]",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function SectionHeader({
  title,
  status,
  children,
}: {
  title: string;
  status: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex items-baseline gap-3 pt-8 pb-1.5">
      <h2 className="m-0 font-hand text-h2 text-ink">{title}</h2>
      <span className="flex-1 border-b border-dashed border-hairline-dashed" />
      <Mono>{status}</Mono>
      {children}
    </div>
  );
}

/** Pending state: hatched panel + a specific reason (never a generic shimmer). */
export function LockedPanel({
  label = "SECTION LOCKED",
  reason,
}: {
  label?: string;
  reason: ReactNode;
}) {
  return (
    <div className="paper-hatched mt-2 rounded-[3px] border-[1.5px] border-dashed border-locked-border px-6 py-9 text-center">
      <Mono className="tracking-data-wide">{label}</Mono>
      <div className="mt-1.5 text-[19px] text-ink-soft">{reason}</div>
    </div>
  );
}

/** Live cue row with marching dashes — shown between turns while the debate streams. */
export function CueRow({ children }: { children: ReactNode }) {
  return (
    <div className="mt-6 flex items-center gap-3 rounded-[3px] border-[1.5px] border-dashed border-locked-border bg-white/70 px-4 py-3">
      <span className="cue-dashes h-1.5 w-6.5 shrink-0 rounded-full" />
      <span className="text-[17px] text-[#5c574e]">{children}</span>
    </div>
  );
}

const STOCK: Record<AgentRole, string[]> = {
  advocate: ["canary", "orange", "gold"],
  skeptic: ["pink", "cyan", "lime"],
};

/** Post-it stock by agent + round: Advocate warm, Skeptic cool. */
export function postitStyle(agent: AgentRole, round: number) {
  return {
    backgroundColor: `var(--color-postit-${STOCK[agent][(round - 1) % 3]})`,
    transform: `rotate(var(--rotate-${agent}))`,
  };
}

export const primaryButton =
  "rounded-paper bg-ink-strong px-5 pt-2 pb-1.5 font-marker text-[27px] leading-none text-paper shadow-button transition hover:bg-[#1f1e1c] active:translate-x-0.5 active:translate-y-0.5 active:shadow-[1px_1px_0_rgba(51,49,46,.22)] disabled:opacity-40";
export const secondaryButton =
  "rounded-paper border-[1.5px] border-ink-strong px-5 pt-2 pb-1.5 font-marker text-[27px] leading-none text-ink-strong hover:bg-chip-bg disabled:opacity-40";

export const DEFAULT_ROUNDS = 2;
const claimKey = (debateId: string) => `argus:claim:${debateId}`;

/** Remembered claim text for a debate (the transcript endpoint doesn't return it). */
export function readStoredClaim(debateId: string): string | null {
  try {
    return sessionStorage.getItem(claimKey(debateId));
  } catch {
    return null;
  }
}

/** Start a debate via the existing api.startDebate, remember the claim, navigate to it. */
export function useStartDebate() {
  const navigate = useNavigate();
  const [pending, setPending] = useState(false);

  async function start(claim: string) {
    const text = claim.trim();
    if (!text || pending) return;
    setPending(true);
    try {
      const { debate_id } = await startDebate(text, DEFAULT_ROUNDS);
      try {
        sessionStorage.setItem(claimKey(debate_id), text);
      } catch {
        /* storage blocked — the sticky bar falls back to the verdict's claim */
      }
      await navigate({ to: "/debate/$debateId", params: { debateId: debate_id } });
    } finally {
      setPending(false);
    }
  }

  return { start, pending };
}
