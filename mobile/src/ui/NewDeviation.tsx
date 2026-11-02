import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput } from 'react-native';
import { captureDeviation } from '../core/capture';
import { outbox, newId } from '../lib/runtime';

export function NewDeviation({ userId, onDone }: { userId: string; onDone: () => void }) {
  const [f, setF] = useState({ title: '', description: '', batchId: '', equipmentId: '', area: '' });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (v: string) => setF({ ...f, [k]: v });

  const save = async () => {
    try {
      await captureDeviation(outbox, userId, f, { newId, now: () => new Date() });
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save');
    }
  };

  return (
    <ScrollView contentContainerStyle={s.wrap} keyboardShouldPersistTaps="handled">
      <Text style={s.h2}>Raise deviation</Text>
      <TextInput style={s.input} placeholder="Title *" value={f.title} onChangeText={set('title')} accessibilityLabel="Title" />
      <TextInput style={[s.input, s.multi]} placeholder="What happened? *" multiline value={f.description} onChangeText={set('description')} accessibilityLabel="Description" />
      <TextInput style={s.input} placeholder="Batch / lot" value={f.batchId} onChangeText={set('batchId')} accessibilityLabel="Batch" />
      <TextInput style={s.input} placeholder="Equipment ID" autoCapitalize="characters" value={f.equipmentId} onChangeText={set('equipmentId')} accessibilityLabel="Equipment" />
      <TextInput style={s.input} placeholder="Area / room" value={f.area} onChangeText={set('area')} accessibilityLabel="Area" />
      {error ? <Text style={s.err}>{error}</Text> : null}
      <Text style={s.hint}>Saved on this device first, then sent when you are online. Photos are not supported yet.</Text>
      <Pressable style={s.btn} onPress={save} accessibilityRole="button"><Text style={s.btnText}>Save</Text></Pressable>
      <Pressable style={s.ghost} onPress={onDone} accessibilityRole="button"><Text>Cancel</Text></Pressable>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  wrap: { padding: 20, gap: 12 },
  h2: { fontSize: 22, fontWeight: '700' },
  input: { borderWidth: 1, borderColor: '#bbb', borderRadius: 8, padding: 12, fontSize: 16 },
  multi: { minHeight: 110, textAlignVertical: 'top' },
  err: { color: '#b00020' },
  hint: { color: '#555' },
  btn: { backgroundColor: '#1d4ed8', padding: 14, borderRadius: 8, alignItems: 'center' },
  btnText: { color: '#fff', fontWeight: '600', fontSize: 16 },
  ghost: { padding: 12, alignItems: 'center' },
});
