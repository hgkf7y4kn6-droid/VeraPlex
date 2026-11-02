import { KV, OutboxItem } from './types';

const KEY = 'veraplex.outbox.v1';

/**
 * Durable outbox. Every mutation runs through one promise chain so a background sync and a user
 * capture can never overwrite each other's writes (read-modify-write is serialized).
 */
export class Outbox {
  private chain: Promise<unknown> = Promise.resolve();
  constructor(private kv: KV) {}

  private async read(): Promise<OutboxItem[]> {
    const raw = await this.kv.getItem(KEY);
    if (!raw) return [];
    try {
      return JSON.parse(raw) as OutboxItem[];
    } catch {
      return []; // corrupt store must not brick the app; items are lost only in this pathological case
    }
  }

  private mutate<T>(fn: (items: OutboxItem[]) => T): Promise<T> {
    const run = this.chain.then(async () => {
      const items = await this.read();
      const out = fn(items);
      await this.kv.setItem(KEY, JSON.stringify(items));
      return out;
    });
    this.chain = run.catch(() => undefined);
    return run;
  }

  list(): Promise<OutboxItem[]> {
    return this.chain.then(() => this.read());
  }

  add(item: OutboxItem): Promise<void> {
    return this.mutate((items) => {
      if (!items.some((i) => i.localId === item.localId)) items.push(item);
    });
  }

  update(localId: string, patch: Partial<OutboxItem>): Promise<void> {
    return this.mutate((items) => {
      const i = items.find((x) => x.localId === localId);
      if (i) Object.assign(i, patch);
    });
  }

  remove(localId: string): Promise<void> {
    return this.mutate((items) => {
      const idx = items.findIndex((x) => x.localId === localId);
      if (idx >= 0) items.splice(idx, 1);
    });
  }

  /** After a crash/kill an item may be stuck 'syncing'. Re-sending is safe because of the idempotency key. */
  recoverInterrupted(): Promise<number> {
    return this.mutate((items) => {
      let n = 0;
      for (const i of items) if (i.status === 'syncing') { i.status = 'pending'; n++; }
      return n;
    });
  }

  /** Drop old synced items so the store does not grow forever. */
  pruneSynced(keep = 20): Promise<void> {
    return this.mutate((items) => {
      const synced = items.filter((i) => i.status === 'synced');
      const drop = new Set(synced.slice(0, Math.max(0, synced.length - keep)).map((i) => i.localId));
      for (let k = items.length - 1; k >= 0; k--) if (drop.has(items[k].localId)) items.splice(k, 1);
    });
  }
}
