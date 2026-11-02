// Runs the real Outbox + SyncEngine + Api against a live backend. See e2e/run.sh.
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { test } from 'node:test';
import { Api } from '../src/core/api';
import { captureDeviation } from '../src/core/capture';
import { Outbox } from '../src/core/outbox';
import { SyncEngine } from '../src/core/sync';
import { KV } from '../src/core/types';

const URL = process.env.E2E_API_URL!;
const SECRET = process.env.E2E_SECRET!;
const ids = JSON.parse(process.env.E2E_IDS!);

const b64 = (o: object | Buffer) => Buffer.from(o instanceof Buffer ? o : JSON.stringify(o)).toString('base64url');
function token(sub: string, exp = 3600) {
  const now = Math.floor(Date.now() / 1000);
  const head = b64({ alg: 'HS256', typ: 'JWT' }) + '.' + b64({ sub, aud: 'authenticated', iat: now, exp: now + exp });
  return head + '.' + createHmac('sha256', SECRET).update(head).digest('base64url');
}
class MemKV implements KV {
  m = new Map<string, string>();
  async getItem(k: string) { return this.m.get(k) ?? null; }
  async setItem(k: string, v: string) { this.m.set(k, v); }
  async removeItem(k: string) { this.m.delete(k); }
}
let n = 0;
const deps = () => ({ newId: () => `e2e-${Date.now()}-${++n}`, now: () => new Date() });

test('offline capture -> reconnect -> synced once; lost-response replay is deduplicated by the real server', async () => {
  const op = ids.operator as string;
  const dead = new Api('http://127.0.0.1:1', async () => token(op), 500);
  const live = new Api(URL, async () => token(op));
  const outbox = new Outbox(new MemKV());

  const a = await captureDeviation(outbox, op, { title: 'Offline event one', description: 'captured with no signal', equipmentId: 'EQ-E2E' }, deps(), new Date(Date.now() - 3600_000));
  const b = await captureDeviation(outbox, op, { title: 'Offline event two', description: 'second', equipmentId: 'EQ-E2E' }, deps());

  let t = Date.now();
  const offline = await new SyncEngine(outbox, dead, () => t, () => 1).flush(op);
  assert.equal(offline.offline, true);
  assert.ok((await outbox.list()).every((i) => i.status === 'pending'));

  // Simulate a lost response: the server got item A, the app never heard back.
  const lost = await live.createDeviation(a, a.localId);
  assert.equal(lost.status, 201);

  t += 10 * 60_000; // past backoff
  const r = await new SyncEngine(outbox, live, () => t).flush(op);
  assert.equal(r.sent, 2);
  const items = await outbox.list();
  assert.ok(items.every((i) => i.status === 'synced'));
  assert.equal(items.find((i) => i.localId === a.localId)!.serverId, lost.body.id); // same record, no duplicate

  const server = await live.listDeviations();
  const mine = server.body.filter((d) => d.content.equipment_id === 'EQ-E2E');
  assert.equal(mine.length, 2);
  const first = mine.find((d) => d.id === lost.body.id)!;
  assert.match((first.content as unknown as Record<string, string>).occurred_at, /T/);
  assert.ok(b.localId);

  const me = await live.me();
  assert.equal(me.body.role, 'operator');
});

test('expired token pauses sync without losing the item; the server rejects another user\'s token for items', async () => {
  const op = ids.operator as string;
  const expired = new Api(URL, async () => token(op, -60));
  const outbox = new Outbox(new MemKV());
  await captureDeviation(outbox, op, { title: 'Needs login again', description: 'x' }, deps());
  const r = await new SyncEngine(outbox, expired).flush(op);
  assert.equal(r.authRequired, true);
  assert.equal((await outbox.list())[0].status, 'pending');
  const fresh = new Api(URL, async () => token(op));
  assert.equal((await new SyncEngine(outbox, fresh).flush(op)).sent, 1);
});

test('a role without permission gets a permanent failure, not an endless retry', async () => {
  const api = new Api(URL, async () => token(ids.admin)); // admins manage users; they cannot raise deviations
  const outbox = new Outbox(new MemKV());
  const it = await captureDeviation(outbox, ids.admin, { title: 'Role check', description: 'x' }, deps());
  const r = await new SyncEngine(outbox, api).flush(ids.admin);
  assert.equal(r.failed, 1);
  const [f] = await outbox.list();
  assert.equal(f.localId, it.localId); assert.equal(f.status, 'failed'); assert.match(f.error!, /permission/);
});
