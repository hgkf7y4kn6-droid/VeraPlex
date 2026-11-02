import NetInfo from '@react-native-community/netinfo';
import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';
import { SyncResult } from '../core/sync';
import { OutboxItem } from '../core/types';
import { engine, outbox } from '../lib/runtime';

/** Keeps the outbox visible and triggers syncs on start, reconnect, foreground, capture and a slow timer. */
export function useOutbox(userId: string | null, onAuthRequired: () => void) {
  const [items, setItems] = useState<OutboxItem[]>([]);
  const [online, setOnline] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const uid = useRef(userId);
  uid.current = userId;

  const reload = useCallback(async () => setItems(await outbox.list()), []);

  const sync = useCallback(async (): Promise<SyncResult | null> => {
    if (!uid.current) return null;
    setSyncing(true);
    try {
      const r = await engine.flush(uid.current);
      if (r.authRequired) onAuthRequired();
      return r;
    } finally {
      setSyncing(false);
      await reload();
    }
  }, [onAuthRequired, reload]);

  useEffect(() => {
    reload();
    void sync();
    const net = NetInfo.addEventListener((s) => {
      const up = !!s.isConnected && s.isInternetReachable !== false;
      setOnline(up);
      if (up) void sync();
    });
    const app = AppState.addEventListener('change', (st) => { if (st === 'active') void sync(); });
    const timer = setInterval(() => void sync(), 30_000);
    return () => { net(); app.remove(); clearInterval(timer); };
  }, [sync, reload, userId]);

  return { items, online, syncing, sync, reload };
}
