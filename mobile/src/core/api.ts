import { DeviationInput, ServerDeviation } from './types';

export class NetworkError extends Error {}

export interface ApiResult<T = unknown> {
  status: number;
  body: T;
}

export interface DeviationApi {
  createDeviation(input: DeviationInput & { occurredAt: string; capturedAt: string }, idempotencyKey: string): Promise<ApiResult<{ id: string }>>;
}

export class Api implements DeviationApi {
  constructor(
    private baseUrl: string,
    private getToken: () => Promise<string | null>,
    private timeoutMs = 15000,
    private fetchImpl: typeof fetch = fetch,
  ) {}

  private async request<T>(path: string, init: RequestInit = {}, extra: Record<string, string> = {}): Promise<ApiResult<T>> {
    const token = await this.getToken();
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), this.timeoutMs);
    try {
      const res = await this.fetchImpl(`${this.baseUrl}/api/v1${path}`, {
        ...init,
        signal: ctl.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...extra,
        },
      });
      let body: unknown = null;
      try { body = await res.json(); } catch { /* empty body */ }
      return { status: res.status, body: body as T };
    } catch (e) {
      throw new NetworkError(e instanceof Error ? e.message : 'network error');
    } finally {
      clearTimeout(timer);
    }
  }

  createDeviation(input: DeviationInput & { occurredAt: string; capturedAt: string }, idempotencyKey: string) {
    return this.request<{ id: string }>(
      '/deviations',
      {
        method: 'POST',
        body: JSON.stringify({
          title: input.title,
          description: input.description,
          batch_id: input.batchId || null,
          equipment_id: input.equipmentId || null,
          area: input.area || null,
          occurred_at: input.occurredAt,
          client_captured_at: input.capturedAt,
        }),
      },
      { 'Idempotency-Key': idempotencyKey },
    );
  }

  listDeviations() {
    return this.request<ServerDeviation[]>('/deviations');
  }

  me() {
    return this.request<{ user_id: string; name: string; role: string; permissions: string[] }>('/me');
  }
}
