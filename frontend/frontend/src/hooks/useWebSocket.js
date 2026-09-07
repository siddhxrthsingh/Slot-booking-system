import { useEffect, useRef, useCallback } from 'react';
import { getWsBaseUrl } from './wsBaseUrl';

/**
 * Connects to the backend WebSocket and calls `onMessage(event)` on each message.
 * Automatically reconnects after disconnects (up to maxRetries times, then gives up).
 */
export function useWebSocket(onMessage, enabled = true) {
  const wsRef        = useRef(null);
  const timerRef     = useRef(null);
  const retryCount   = useRef(0);
  const onMsgRef     = useRef(onMessage);

  // Keep the callback ref fresh without triggering reconnects
  useEffect(() => { onMsgRef.current = onMessage; }, [onMessage]);

  const connect = useCallback(() => {
    if (!enabled) return;

    const url = `${getWsBaseUrl()}/ws`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      retryCount.current = 0;
    };

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        onMsgRef.current?.(msg);
      } catch {
        // ignore malformed frames
      }
    };

    ws.onclose = () => {
      wsRef.current = null;
      if (!enabled) return;
      retryCount.current += 1;
      if (retryCount.current > 10) return; // give up after 10 retries
      const delay = Math.min(1000 * retryCount.current, 10000);
      timerRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [enabled]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);
}
