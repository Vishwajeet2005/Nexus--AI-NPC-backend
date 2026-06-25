import { useCallback, useEffect, useRef, useState } from "react";
import { getToken } from "../api/nexus";
import type { EmotionalState, NPCBehaviour } from "../api/nexus";

const WS_URL = (import.meta.env.VITE_WS_URL as string | undefined) ?? "ws://localhost:8000";

export interface NPCStateUpdate {
  npc_id: string;
  npc_name: string;
  behaviour: NPCBehaviour;
  emotional_state: EmotionalState;
  secret_leaked: string | null;
}

export interface UseNexusWSResult {
  connected: boolean;
  lastNpcUpdate: NPCStateUpdate | null;
  recentEvents: Array<{ type: string; data: Record<string, unknown>; ts: number }>;
}

/**
 * useNexusWS — connects to the session's WebSocket channel and provides
 * live NPC state updates and recent event history.
 *
 * Implements the server's auth-first handshake (sends
 * `{ "type": "auth", "token": ... }` on open) and auto-replies to pings.
 *
 * Reconnects automatically with exponential back-off on unexpected disconnects.
 */
export function useNexusWS(sessionId: string | null): UseNexusWSResult {
  const [connected, setConnected] = useState(false);
  const [lastNpcUpdate, setLastNpcUpdate] = useState<NPCStateUpdate | null>(null);
  const [recentEvents, setRecentEvents] = useState<UseNexusWSResult["recentEvents"]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const retryDelayRef = useRef(1000);
  const unmountedRef = useRef(false);

  const connect = useCallback(() => {
    if (!sessionId || unmountedRef.current) return;

    const token = getToken();
    if (!token) return;

    const ws = new WebSocket(`${WS_URL}/v1/realtime/${sessionId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "auth", token }));
    };

    ws.onmessage = (ev: MessageEvent<string>) => {
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(ev.data) as Record<string, unknown>;
      } catch {
        return;
      }

      const type = (msg.type ?? msg.event) as string | undefined;
      if (!type) return;

      if (type === "connected") {
        setConnected(true);
        retryDelayRef.current = 1000;
        return;
      }

      if (type === "ping") {
        ws.send(JSON.stringify({ type: "pong" }));
        return;
      }

      if (type === "npc_state_changed") {
        const payload = msg.payload as NPCStateUpdate;
        setLastNpcUpdate(payload);
      }

      setRecentEvents((prev) => [
        { type, data: (msg.payload ?? msg.data ?? {}) as Record<string, unknown>, ts: Date.now() },
        ...prev.slice(0, 49),
      ]);
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      if (unmountedRef.current) return;
      // Exponential back-off, max 30s
      const delay = Math.min(retryDelayRef.current, 30_000);
      retryDelayRef.current = Math.min(delay * 2, 30_000);
      setTimeout(connect, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [sessionId]);

  useEffect(() => {
    unmountedRef.current = false;
    connect();
    return () => {
      unmountedRef.current = true;
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  return { connected, lastNpcUpdate, recentEvents };
}
