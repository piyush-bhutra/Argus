import { useEffect, useMemo, useRef, useState } from "react";
import type { DebateGraph } from "@/lib/types";

interface Props {
  graph: DebateGraph;
  survivors: Set<string>;
  selectedId?: string | null | undefined;
  onSelect?: ((id: string) => void) | undefined;
}

const WIDTH = 640;
const HEIGHT = 420;

interface Sim {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

/** Deterministic seeded layout so SSR and client agree, then relaxed with a
 *  small force simulation on the client. */
function seedPositions(ids: string[]): Sim[] {
  return ids.map((id, i) => {
    const angle = (i / Math.max(ids.length, 1)) * Math.PI * 2;
    return {
      id,
      x: WIDTH / 2 + Math.cos(angle) * 150,
      y: HEIGHT / 2 + Math.sin(angle) * 130,
      vx: 0,
      vy: 0,
    };
  });
}

export function ArgumentGraph({ graph, survivors, selectedId, onSelect }: Props) {
  const ids = useMemo(() => graph.nodes.map((n) => n.id), [graph.nodes]);
  const [nodes, setNodes] = useState<Sim[]>(() => seedPositions(ids));
  const frame = useRef<number | null>(null);

  useEffect(() => {
    setNodes(seedPositions(ids));
  }, [ids]);

  useEffect(() => {
    let alpha = 1;
    const step = () => {
      setNodes((prev) => {
        const next = prev.map((n) => ({ ...n }));
        const byId = new Map(next.map((n) => [n.id, n]));
        // repulsion
        for (let i = 0; i < next.length; i++) {
          for (let j = i + 1; j < next.length; j++) {
            const a = next[i]!;
            const b = next[j]!;
            let dx = b.x - a.x;
            let dy = b.y - a.y;
            let d2 = dx * dx + dy * dy || 0.01;
            const f = 9000 / d2;
            const d = Math.sqrt(d2);
            dx /= d;
            dy /= d;
            a.vx -= dx * f;
            a.vy -= dy * f;
            b.vx += dx * f;
            b.vy += dy * f;
          }
        }
        // spring along edges
        for (const e of graph.edges) {
          const a = byId.get(e.source);
          const b = byId.get(e.target);
          if (!a || !b) continue;
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const d = Math.hypot(dx, dy) || 0.01;
          const f = (d - 140) * 0.02;
          a.vx += (dx / d) * f;
          a.vy += (dy / d) * f;
          b.vx -= (dx / d) * f;
          b.vy -= (dy / d) * f;
        }
        for (const n of next) {
          // gentle centering
          n.vx += (WIDTH / 2 - n.x) * 0.006;
          n.vy += (HEIGHT / 2 - n.y) * 0.006;
          n.vx *= 0.82;
          n.vy *= 0.82;
          n.x = Math.min(WIDTH - 40, Math.max(40, n.x + n.vx * alpha));
          n.y = Math.min(HEIGHT - 40, Math.max(40, n.y + n.vy * alpha));
        }
        return next;
      });
      alpha *= 0.985;
      if (alpha > 0.02) frame.current = requestAnimationFrame(step);
    };
    frame.current = requestAnimationFrame(step);
    return () => {
      if (frame.current) cancelAnimationFrame(frame.current);
    };
  }, [graph.edges, ids]);

  const pos = new Map(nodes.map((n) => [n.id, n]));

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="grid-backdrop h-[420px] w-full rounded-lg border border-border bg-surface"
      role="img"
      aria-label="Argument attack graph"
    >
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="currentColor" className="text-muted-foreground" />
        </marker>
      </defs>

      {graph.edges.map((e, i) => {
        const a = pos.get(e.source);
        const b = pos.get(e.target);
        if (!a || !b) return null;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const d = Math.hypot(dx, dy) || 1;
        const ox = (dx / d) * 22;
        const oy = (dy / d) * 22;
        return (
          <line
            key={i}
            x1={a.x + ox}
            y1={a.y + oy}
            x2={b.x - ox}
            y2={b.y - oy}
            stroke="currentColor"
            className="text-border"
            strokeWidth={1.5}
            markerEnd="url(#arrow)"
          />
        );
      })}

      {graph.nodes.map((n) => {
        const p = pos.get(n.id);
        if (!p) return null;
        const advocate = n.agent === "advocate";
        const color = advocate ? "var(--advocate)" : "var(--skeptic)";
        const survived = survivors.has(n.id);
        return (
          <g
            key={n.id}
            transform={`translate(${p.x}, ${p.y})`}
            onClick={() => onSelect?.(n.id)}
            className="cursor-pointer"
          >
            {advocate ? (
              <circle
                r={20}
                fill={color}
                fillOpacity={0.16}
                stroke={color}
                strokeWidth={selectedId === n.id ? 3 : 1.6}
              />
            ) : (
              <rect
                x={-18}
                y={-18}
                width={36}
                height={36}
                rx={4}
                fill={color}
                fillOpacity={0.16}
                stroke={color}
                strokeWidth={selectedId === n.id ? 3 : 1.6}
              />
            )}
            {survived && (
              <circle r={26} fill="none" stroke="var(--survived)" strokeWidth={1} strokeDasharray="3 3" />
            )}
            <text
              textAnchor="middle"
              dy="4"
              fontSize="11"
              fontFamily="var(--font-mono)"
              fill={color}
            >
              {n.label ?? n.id}
            </text>
            <text
              textAnchor="middle"
              dy="34"
              fontSize="9"
              fontFamily="var(--font-mono)"
              fill="var(--muted-foreground)"
            >
              r{n.round}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
