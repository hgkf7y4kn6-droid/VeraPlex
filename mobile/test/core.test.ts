import assert from 'node:assert/strict';
import { test } from 'node:test';
import { NetworkError, DeviationApi, ApiResult } from '../src/core/api';
import { captureDeviation } from '../src/core/capture';
import { Outbox } from '../src/core/outbox';
import { backoff, SyncEngine } from '../src/core/sync';
import { KV } from '../src/core/types';

class MemKV implements KV {
  m = new Map<string, string>();
  async getItem(k: string) { return this.m.get(k) ?? null; }
  async setItem(k: string, v: string) { await new Promise((r) => setTimeout(r, 1)); this.m.set(k, v); }
  async removeItem(k: string) { this.m.delete(k); }
}

let n = 0;
const deps = () => ({ newId: () => `local-id-${++n}-xxxxxxxx`, now: () => new Date('2026-11-02T10:00:00Z') });
const input = { title: 'Leak at filler', description: 'Seal weeping', equipmentId: 'EQ-7' };

type Handler = (key: string, calls: string[]) => ApiResult<{ id: string }> | Promise<ApiResult<{ id: string }>>;
function fakeApi(handler: Handler) {
  const calls: string[] = [];
  const api: DeviationApi = { createDeviation: async (_i, key) => { calls.push(key); return handler(key, calls); } };
  return { api, calls };
}
const ok = (id = 'srv-1', status = 201): ApiResult<{ id: string }> => ({ status, body: { id } });

test('capture is local-first, validated, and survives a restart', async () => {
  const kv = new MemKV();
  const a = new Outbox(kv);
  await assert.rejects(captureDeviation(a, 'u1', { title: 'x', description: 'y' }, deps()), /Title/);
  const it = await captureDeviation(a, 'u1', input, deps());
  const b = new Outbox(kv); // "restart"
  const [back] = await b.list();
  assert.equal(back.localId, it.localId);
  assert.equal(back.status, 'pending');
});

test('success marks synced and uses localId as idempotency key', async () => {
  const outbox = new Outbox(new MemKV());
  const it = await captureDeviation(outbox, 'u1', input, deps());
  const { api, calls } = fakeApi(() => ok());
  const r = await new SyncEngine(outbox, api).flush('u1');
  assert.equal(r.sent, 1);
  assert.deepEqual(calls, [it.localId]);
  const [s] = await outbox.list();
  assert.equal(s.status, 'synced'); assert.equal(s.serverId, 'srv-1');
});

test('lost response then retry is safe: server answers 200 for a known key', async () => {
  const outbox = new Outbox(new MemKV());
  await captureDeviation(outbox, 'u1', input, deps());
  let first = true;
  const { api, calls } = fakeApi(() => { if (first) { first = false; throw new NetworkError('timeout'); } return ok('srv-9', 200); });
  let t = 1_000_000;
  const eng = new SyncEngine(outbox, api, () => t, () => 1);
  const r1 = await eng.flush('u1');
  assert.equal(r1.offline, true);
  assert.equal((await outbox.list())[0].status, 'pending');
  assert.equal((await eng.flush('u1')).sent, 0); // still backing off
  t += 60_000;
  assert.equal((await eng.flush('u1')).sent, 1);
  assert.equal(calls[0], calls[1]); // same key both times
  assert.equal((await outbox.list())[0].serverId, 'srv-9');
});

test('backoff grows, is capped, and jitters', () => {
  assert.ok(backoff(1, () => 1) <= 5_000);
  assert.ok(backoff(3, () => 1) === 20_000);
  assert.ok(backoff(30, () => 1) <= 15 * 60_000);
  assert.ok(backoff(4, () => 0) < backoff(4, () => 1));
});

test('401 stops the flush and keeps items pending without burning attempts', async () => {
  const outbox = new Outbox(new MemKV());
  await captureDeviation(outbox, 'u1', input, deps());
  await captureDeviation(outbox, 'u1', input, deps());
  const { api, calls } = fakeApi(() => ({ status: 401, body: { id: '' } }));
  const r = await new SyncEngine(outbox, api).flush('u1');
  assert.equal(r.authRequired, true); assert.equal(calls.length, 1);
  const items = await outbox.list();
  assert.ok(items.every((i) => i.status === 'pending' && i.attempts === 0));
});

test('validation/permission errors become failed (not retried forever) and can be fixed and retried', async () => {
  const outbox = new Outbox(new MemKV());
  const it = await captureDeviation(outbox, 'u1', input, deps());
  let status = 422;
  const { api } = fakeApi(() => status === 422
    ? ({ status: 422, body: { detail: [{ loc: ['body', 'title'], msg: 'too short' }] } } as never)
    : ok());
  const eng = new SyncEngine(outbox, api);
  const r = await eng.flush('u1');
  assert.equal(r.failed, 1);
  let [f] = await outbox.list();
  assert.equal(f.status, 'failed'); assert.match(f.error!, /title: too short/);
  assert.equal((await eng.flush('u1')).sent, 0);
  status = 201;
  await eng.retry(it.localId, { title: 'Longer title now' });
  assert.equal((await eng.flush('u1')).sent, 1);
});

test('5xx retries with backoff; other items still go through after a per-item failure', async () => {
  const outbox = new Outbox(new MemKV());
  const a = await captureDeviation(outbox, 'u1', input, { ...deps(), now: () => new Date('2026-11-02T10:00:00Z') });
  const b = await captureDeviation(outbox, 'u1', input, { ...deps(), now: () => new Date('2026-11-02T10:01:00Z') });
  const { api } = fakeApi((key) => (key === a.localId ? ({ status: 503, body: {} } as never) : ok('srv-b')));
  const r = await new SyncEngine(outbox, api, () => 5_000).flush('u1');
  assert.deepEqual([r.sent, r.retryLater], [1, 1]);
  const items = await outbox.list();
  assert.equal(items.find((i) => i.localId === a.localId)!.attempts, 1);
  assert.equal(items.find((i) => i.localId === b.localId)!.status, 'synced');
});

test('never sends another user\'s captured items with the current session', async () => {
  const outbox = new Outbox(new MemKV());
  await captureDeviation(outbox, 'alice', input, deps());
  const { api, calls } = fakeApi(() => ok());
  const r = await new SyncEngine(outbox, api).flush('bob');
  assert.equal(calls.length, 0); assert.equal(r.sent, 0);
  assert.equal((await outbox.list())[0].status, 'pending');
});

test('interrupted (killed mid-send) items are recovered and resent with the same key', async () => {
  const kv = new MemKV();
  const outbox = new Outbox(kv);
  const it = await captureDeviation(outbox, 'u1', input, deps());
  await outbox.update(it.localId, { status: 'syncing' }); // app was killed here
  const { api, calls } = fakeApi(() => ok('srv-1', 200));
  const r = await new SyncEngine(new Outbox(kv), api).flush('u1');
  assert.equal(r.sent, 1); assert.deepEqual(calls, [it.localId]);
});

test('concurrent flushes do not double-send, and captures during a flush are not lost', async () => {
  const outbox = new Outbox(new MemKV());
  await captureDeviation(outbox, 'u1', input, deps());
  let release!: () => void;
  const gate = new Promise<void>((r) => { release = r; });
  const { api, calls } = fakeApi(async () => { await gate; return ok(); });
  const eng = new SyncEngine(outbox, api);
  const f1 = eng.flush('u1');
  await new Promise((r) => setTimeout(r, 20));
  const f2 = await eng.flush('u1');
  assert.equal(f2.skipped, true);
  const added = await captureDeviation(outbox, 'u1', { ...input, title: 'Captured mid-flush' }, deps());
  release();
  assert.equal((await f1).sent, 1);
  assert.equal(calls.length, 1);
  const items = await outbox.list();
  assert.equal(items.length, 2);
  assert.equal(items.find((i) => i.localId === added.localId)!.status, 'pending');
});

test('duplicate adds of the same localId are ignored; synced items are pruned', async () => {
  const outbox = new Outbox(new MemKV());
  const it = await captureDeviation(outbox, 'u1', input, deps());
  await outbox.add(it);
  assert.equal((await outbox.list()).length, 1);
  for (let i = 0; i < 25; i++) await outbox.add({ ...it, localId: `s-${i}-xxxxxxxxx`, status: 'synced' });
  await outbox.pruneSynced(20);
  assert.equal((await outbox.list()).filter((i) => i.status === 'synced').length, 20);
});
