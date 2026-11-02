import { NetworkError, DeviationApi } from './api';
import { Outbox } from './outbox';
import { OutboxItem } from './types';

export interface SyncResult {
  sent: number;
  failed: number;
  retryLater: number;
  authRequired: boolean;
  offline: boolean;
  skipped: boolean; // another flush was already running
}

const BASE_DELAY_MS = 5_000;
const MAX_DELAY_MS = 15 * 60_000;

export function backoff(attempts: number, rand: () => number = Math.random): number {
  const exp = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** Math.max(0, attempts - 1));
  return Math.round(exp * (0.5 + rand() / 2)); // 50-100% jitter avoids thundering herds
}

/** Statuses that will never succeed by retrying: show them to the user instead. */
const PERMANENT = new Set([400, 403, 404, 409, 413, 422]);

export class SyncEngine {
  private running = false;
  constructor(
    private outbox: Outbox,
    private api: DeviationApi,
    private now: () => number = Date.now,
    private rand: () => number = Math.random,
  ) {}

  async flush(currentUserId: string): Promise<SyncResult> {
    const result: SyncResult = { sent: 0, failed: 0, retryLater: 0, authRequired: false, offline: false, skipped: false };
    if (this.running) return { ...result, skipped: true };
    this.running = true;
    try {
      await this.outbox.recoverInterrupted();
      const due = (await this.outbox.list())
        .filter((i) => i.status === 'pending' && i.userId === currentUserId && i.nextAttemptAt <= this.now())
        .sort((a, b) => a.capturedAt.localeCompare(b.capturedAt));
      for (const item of due) {
        const stop = await this.send(item, result);
        if (stop) break;
      }
      await this.outbox.pruneSynced();
      return result;
    } finally {
      this.running = false;
    }
  }

  /** Returns true when the whole flush should stop (offline or signed out). */
  private async send(item: OutboxItem, result: SyncResult): Promise<boolean> {
    await this.outbox.update(item.localId, { status: 'syncing' });
    try {
      const res = await this.api.createDeviation(item, item.localId);
      if (res.status === 200 || res.status === 201) {
        // 200 = the server already had this key (a retry after a lost response): still success
        await this.outbox.update(item.localId, { status: 'synced', serverId: res.body.id, error: undefined });
        result.sent++;
        return false;
      }
      if (res.status === 401) {
        await this.outbox.update(item.localId, { status: 'pending' });
        result.authRequired = true;
        return true;
      }
      const detail = errorText(res.body) ?? `HTTP ${res.status}`;
      if (PERMANENT.has(res.status)) {
        await this.outbox.update(item.localId, { status: 'failed', error: detail });
        result.failed++;
        return false;
      }
      // 5xx, 429, anything unexpected: retry with backoff
      await this.defer(item, detail);
      result.retryLater++;
      return false;
    } catch (e) {
      if (e instanceof NetworkError) {
        await this.defer(item, e.message);
        result.offline = true;
        result.retryLater++;
        return true; // the rest would fail the same way
      }
      throw e;
    }
  }

  private async defer(item: OutboxItem, error: string) {
    const attempts = item.attempts + 1;
    await this.outbox.update(item.localId, {
      status: 'pending', attempts, error, nextAttemptAt: this.now() + backoff(attempts, this.rand),
    });
  }

  /** User fixed a failed item or wants to retry now. */
  async retry(localId: string, patch: Partial<OutboxItem> = {}) {
    await this.outbox.update(localId, { ...patch, status: 'pending', attempts: 0, nextAttemptAt: 0, error: undefined });
  }
}

function errorText(body: unknown): string | undefined {
  const d = (body as { detail?: unknown } | null)?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => `${(x as { loc?: string[] }).loc?.slice(-1)[0] ?? ''}: ${(x as { msg?: string }).msg ?? ''}`).join('; ');
  return undefined;
}
