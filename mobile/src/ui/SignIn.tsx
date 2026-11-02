import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { supabase } from '../lib/supabase';

export function SignIn({ notice }: { notice?: string }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true); setError(null);
    const { error: e } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    if (e) setError(e.message);
    setBusy(false);
  };

  return (
    <View style={s.wrap}>
      <Text style={s.h1}>VeraPlex</Text>
      {notice ? <Text style={s.notice}>{notice}</Text> : null}
      <TextInput style={s.input} placeholder="Email" autoCapitalize="none" keyboardType="email-address" value={email} onChangeText={setEmail} accessibilityLabel="Email" />
      <TextInput style={s.input} placeholder="Password" secureTextEntry value={password} onChangeText={setPassword} accessibilityLabel="Password" />
      {error ? <Text style={s.err}>{error}</Text> : null}
      <Pressable style={s.btn} onPress={submit} disabled={busy} accessibilityRole="button">
        {busy ? <ActivityIndicator color="#fff" /> : <Text style={s.btnText}>Sign in</Text>}
      </Pressable>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, justifyContent: 'center', padding: 24, gap: 12 },
  h1: { fontSize: 28, fontWeight: '700', marginBottom: 8 },
  notice: { backgroundColor: '#fff4d6', padding: 10, borderRadius: 6 },
  input: { borderWidth: 1, borderColor: '#bbb', borderRadius: 8, padding: 12, fontSize: 16 },
  err: { color: '#b00020' },
  btn: { backgroundColor: '#1d4ed8', padding: 14, borderRadius: 8, alignItems: 'center' },
  btnText: { color: '#fff', fontWeight: '600', fontSize: 16 },
});
