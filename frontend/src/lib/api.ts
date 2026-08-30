import type { DebateGraph, Transcript, Verdict } from "./types";
import { MOCK_DEBATE_ID, mockGraph, mockTranscript, mockVerdict } from "./mock-data";

export const API_BASE_URL =
  (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "http://localhost:8000";

/** Flips to true the first time a request falls back to bundled mock data, so
 *  the UI can show a "backend offline" indicator and a live run is never
 *  mistaken for demo data. */
export const apiState: { usingMock: boolean } = { usingMock: false };

/**
 * Thin fetch wrapper. If the backend is unreachable (or the demo debate id is
 * used), we fall back to mock data so the dashboard stays fully navigable.
 */
async function request<T>(path: string, init?: RequestInit, fallback?: () => T): Promise<T> {
  try {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return (await res.json()) as T;
  } catch (error) {
    if (fallback) {
      console.warn(`[api] falling back to mock data for ${path}`, error);
      apiState.usingMock = true;
      return fallback();
    }
    throw error;
  }
}

export function startDebate(claim: string, rounds = 3) {
  return request<{ debate_id: string }>(
    "/debate/start",
    { method: "POST", body: JSON.stringify({ claim, rounds }) },
    () => ({ debate_id: MOCK_DEBATE_ID }),
  );
}

export function getTranscript(debateId: string) {
  return request<Transcript>(`/debate/${debateId}/transcript`, undefined, () => mockTranscript);
}

export function getGraph(debateId: string) {
  return request<DebateGraph>(`/debate/${debateId}/graph`, undefined, () => mockGraph);
}

export function getVerdict(debateId: string) {
  return request<Verdict>(`/debate/${debateId}/verdict`, undefined, () => mockVerdict);
}
