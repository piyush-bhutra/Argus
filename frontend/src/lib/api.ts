import type { DebateGraph, Transcript, Verdict } from "./types";
import { MOCK_DEBATE_ID, mockGraph, mockTranscript, mockVerdict } from "./mock-data";

export const API_BASE_URL =
  (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "http://localhost:8000";

/** Flips to true only when the backend is genuinely unreachable and we fall
 *  back to bundled mock data — so a live run is never mistaken for demo data. */
export const apiState: { usingMock: boolean } = { usingMock: false };

/** Thrown when the backend responds with an HTTP error (it IS reachable). */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * Thin fetch wrapper.
 *  - Network failure (backend down): fall back to bundled mock data if a
 *    fallback is provided, and flip `apiState.usingMock`.
 *  - HTTP error (backend up, request failed — e.g. a debate that hit a rate
 *    limit): throw `ApiError`. We do NOT show mock data here, because that
 *    would present a stale demo result as if it were the user's live debate.
 */
async function request<T>(path: string, init?: RequestInit, fallback?: () => T): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch (networkError) {
    if (fallback) {
      console.warn(`[api] backend unreachable, using mock data for ${path}`, networkError);
      apiState.usingMock = true;
      return fallback();
    }
    throw networkError;
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* body wasn't JSON — keep statusText */
    }
    throw new ApiError(res.status, detail);
  }

  return (await res.json()) as T;
}

export function startDebate(claim: string, rounds = 2) {
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
