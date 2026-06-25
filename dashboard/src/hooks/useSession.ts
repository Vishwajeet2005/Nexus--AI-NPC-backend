import { useCallback, useEffect, useState } from "react";
import { api } from "../api/nexus";
import type { NPC, Session } from "../api/nexus";

interface UseSessionResult {
  session: Session | null;
  npcs: NPC[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

/**
 * useSession — loads a session's full details and its NPC list.
 *
 * Polls every 10 seconds so the player count and session status stay
 * reasonably fresh in the UI without hammering the API. Real-time NPC
 * state changes are handled by useNexusWS in the NPCMonitor page, not here.
 */
export function useSession(sessionId: string | null): UseSessionResult {
  const [session, setSession] = useState<Session | null>(null);
  const [npcs, setNpcs] = useState<NPC[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const [sess, npcList] = await Promise.all([
        api.sessions.get(sessionId),
        api.npcs.listInSession(sessionId),
      ]);
      setSession(sess);
      setNpcs(npcList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void fetch();
    const interval = setInterval(() => { void fetch(); }, 10_000);
    return () => clearInterval(interval);
  }, [fetch]);

  return { session, npcs, loading, error, refresh: fetch };
}
