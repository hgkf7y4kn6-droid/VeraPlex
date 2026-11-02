export type OutboxStatus = 'pending' | 'syncing' | 'synced' | 'failed';

export interface DeviationInput {
  title: string;
  description: string;
  batchId?: string;
  equipmentId?: string;
  area?: string;
}

/** One captured deviation waiting to reach the server. `localId` doubles as the Idempotency-Key. */
export interface OutboxItem extends DeviationInput {
  localId: string;
  userId: string;
  occurredAt: string; // when the operator says it happened (claim)
  capturedAt: string; // device clock at capture (claim; the server stamps authoritative time)
  status: OutboxStatus;
  attempts: number;
  nextAttemptAt: number; // epoch ms
  serverId?: string;
  error?: string;
}

export interface KV {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

export interface ServerDeviation {
  id: string;
  state: string;
  content: { title: string; description: string; equipment_id?: string | null; batch_id?: string | null };
  recurring: boolean;
  classification: string | null;
}
