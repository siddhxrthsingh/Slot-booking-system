import { useEffect, useRef, useCallback } from 'react';

/**
 * Connects to the authenticated /ws/occupancy endpoint and keeps the
 * subscription in sync with `slotIds`. Calls `onUpdate(data)` for each
 * occupancy_update event, where `data` is { slot_id, booked_count,
 * available_count, status, capacity }.
 *
 * Reconnects automatically (capped backoff, gives up after 10 tries) and
 * re-subscribes to the current slot IDs once reconnected.
 */
export function useOccupancySocket(slotIds, onUpdate, enabled = true) {
  const wsRef          = useRef(null);
  const timerRef        = useRef(null);
  const retryCount      = useRef(0);
  const subscribedRef   = useRef(new Set());
  const onUpdateRef     = useRef(onUpdate);
  const slotIdsRef      = useRef(slotIds);

  useEffect(() => { onUpdateRef.current = onUpdate; }, [onUpdate]);
  useEffect(() => { slotIdsRef.current = slotIds; }, [slotIds]);

  const syncSubscription = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    const wanted = new Set(slotIdsRef.current);
    const current = subscribedRef.current;
    const toSub   = [...wanted].filter((id) => !current.has(id));
    const toUnsub = [...current].filter((id) => !wanted.has(id));

    if (toSub.length) {
      ws.send(JSON.stringify({ action: 'subscribe', slot_ids: toSub }));
      toSub.forEach((id) => current.add(id));
    }
    if (toUnsub.length) {
      ws.send(JSON.stringify({ action: 'unsubscribe', slot_ids: toUnsub }));
      toUnsub.forEach((id) => current.delete(id));
    }
  }, []);

  const connect = useCallback(() => {
    if (!enabled) return;
    const token = sessionStorage.getItem('access_token');
    if (!token) return;

    // Avoid duplicate connections if one is already open/connecting.
    if (wsRef.current) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/occupancy?token=${encodeURIComponent(token)}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      retryCount.current = 0;
      subscribedRef.current = new Set(); // fresh connection has no server-side subscriptions yet
      syncSubscription();
    };

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'occupancy_update') {
          onUpdateRef.current?.(msg.data);
        }
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
  }, [enabled, syncSubscription]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(timerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
      subscribedRef.current = new Set();
    };
  }, [connect]);

  // Keep the server-side subscription in sync whenever the displayed slot
  // set changes (e.g. after a slot refetch), without reconnecting.
  useEffect(() => {
    syncSubscription();
  }, [slotIds, syncSubscription]);
}
