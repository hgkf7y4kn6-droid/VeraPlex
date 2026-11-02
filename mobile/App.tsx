import { Session } from '@supabase/supabase-js';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, SafeAreaView } from 'react-native';
import { api } from './src/lib/runtime';
import { supabase } from './src/lib/supabase';
import { Home } from './src/ui/Home';
import { NewDeviation } from './src/ui/NewDeviation';
import { SignIn } from './src/ui/SignIn';
import { useOutbox } from './src/ui/useOutbox';

export default function App() {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const [name, setName] = useState('');
  const [screen, setScreen] = useState<'home' | 'new'>('home');
  const [notice, setNotice] = useState<string>();

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  const userId = session?.user.id ?? null;
  // Queued items stay on the device across sign-out; they only ever send under the same user's session.
  const onAuthRequired = useCallback(() => setNotice('Your session expired. Sign in again to send saved deviations.'), []);
  const { items, online, syncing, sync, reload } = useOutbox(userId, onAuthRequired);

  useEffect(() => {
    if (!userId) return;
    api.me().then((r) => { if (r.status === 200) setName(r.body.name); }).catch(() => undefined);
  }, [userId]);

  if (session === undefined) return <ActivityIndicator style={{ flex: 1 }} />;
  return (
    <SafeAreaView style={{ flex: 1 }}>
      <StatusBar style="auto" />
      {!session ? (
        <SignIn notice={notice} />
      ) : screen === 'new' ? (
        <NewDeviation userId={session.user.id} onDone={async () => { setScreen('home'); await reload(); void sync(); }} />
      ) : (
        <Home name={name || session.user.email || ''} items={items} online={online} syncing={syncing}
              onSync={sync} onReload={reload} onNew={() => setScreen('new')} />
      )}
    </SafeAreaView>
  );
}
