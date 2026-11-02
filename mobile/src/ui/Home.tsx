import { useEffect, useState } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { OutboxItem, ServerDeviation } from '../core/types';
import { api, engine } from '../lib/runtime';
import { supabase } from '../lib/supabase';

const CACHE = 'veraplex.deviations.cache.v1';
const label: Record<string, string> = { pending: 'Waiting to send', syncing: 'Sending…', failed: 'Needs attention', synced: 'Sent' };

export function Home(props: {
  name: string; items: OutboxItem[]; online: boolean; syncing: boolean;
  onSync: () => Promise<unknown>; onReload: () => Promise<void>; onNew: () => void;
}) {
  const [server, setServer] = useState<ServerDeviation[]>([]);
  const [stale, setStale] = useState(false);

  const load = async () => {
    try {
      const r = await api.listDeviations();
      if (r.status === 200) {
        setServer(r.body); setStale(false);
        await AsyncStorage.setItem(CACHE, JSON.stringify(r.body));
        return;
      }
    } catch { /* offline: fall through to cache */ }
    const cached = await AsyncStorage.getItem(CACHE);
    if (cached) setServer(JSON.parse(cached));
    setStale(true);
  };
  useEffect(() => { void load(); }, [props.items.filter((i) => i.status === 'synced').length]);

  const open = props.items.filter((i) => i.status !== 'synced');
  const serverRows = server;

  return (
    <View style={s.wrap}>
      <View style={s.bar}>
        <Text style={s.hi}>Hi {props.name}</Text>
        <Pressable onPress={() => supabase.auth.signOut()} accessibilityRole="button"><Text style={s.link}>Sign out</Text></Pressable>
      </View>
      {!props.online ? <Text style={s.offline}>Offline — new deviations are saved on this device and sent later.</Text> : null}
      {open.length > 0 ? <Text style={s.pend}>{open.length} not yet on the server</Text> : null}
      <Pressable style={s.btn} onPress={props.onNew} accessibilityRole="button"><Text style={s.btnText}>Raise deviation</Text></Pressable>
      <FlatList
        refreshControl={<RefreshControl refreshing={props.syncing} onRefresh={async () => { await props.onSync(); await load(); }} />}
        data={[...open.map((o) => ({ kind: 'local' as const, o })), ...serverRows.map((d) => ({ kind: 'server' as const, d }))]}
        keyExtractor={(r) => (r.kind === 'local' ? r.o.localId : r.d.id)}
        ListFooterComponent={stale ? <Text style={s.stale}>Showing saved copy; could not reach the server.</Text> : undefined}
        renderItem={({ item: r }) =>
          r.kind === 'local' ? (
            <View style={[s.row, r.o.status === 'failed' && s.rowBad]}>
              <Text style={s.title}>{r.o.title}</Text>
              <Text style={s.meta}>{label[r.o.status]}{r.o.error ? ` — ${r.o.error}` : ''}</Text>
              {r.o.status === 'failed' ? (
                <Pressable onPress={async () => { await engine.retry(r.o.localId); await props.onSync(); }} accessibilityRole="button"><Text style={s.link}>Retry</Text></Pressable>
              ) : null}
            </View>
          ) : (
            <View style={s.row}>
              <Text style={s.title}>{r.d.content.title}</Text>
              <Text style={s.meta}>{r.d.state}{r.d.classification ? ` · ${r.d.classification}` : ''}{r.d.recurring ? ' · recurring' : ''}</Text>
            </View>
          )}
      />
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, padding: 16, gap: 10 },
  bar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  hi: { fontSize: 18, fontWeight: '600' },
  link: { color: '#1d4ed8', fontWeight: '600' },
  offline: { backgroundColor: '#fff4d6', padding: 10, borderRadius: 6 },
  pend: { color: '#7a4b00' },
  stale: { color: '#777', padding: 8 },
  btn: { backgroundColor: '#1d4ed8', padding: 14, borderRadius: 8, alignItems: 'center' },
  btnText: { color: '#fff', fontWeight: '600', fontSize: 16 },
  row: { padding: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: '#ccc', gap: 2 },
  rowBad: { backgroundColor: '#fde8e8' },
  title: { fontSize: 16, fontWeight: '600' },
  meta: { color: '#555' },
});
