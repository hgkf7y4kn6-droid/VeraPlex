import { Outbox } from './outbox';
import { DeviationInput, OutboxItem } from './types';

export interface CaptureDeps {
  newId: () => string;
  now: () => Date;
}

export function validate(input: DeviationInput): string | null {
  if (input.title.trim().length < 3) return 'Title needs at least 3 characters.';
  if (!input.description.trim()) return 'Describe what happened.';
  return null;
}

/** Saves locally first, always. Network is never on the capture path. */
export async function captureDeviation(
  outbox: Outbox, userId: string, input: DeviationInput, deps: CaptureDeps, occurredAt?: Date,
): Promise<OutboxItem> {
  const err = validate(input);
  if (err) throw new Error(err);
  const now = deps.now();
  const item: OutboxItem = {
    ...input,
    title: input.title.trim(),
    description: input.description.trim(),
    localId: deps.newId(),
    userId,
    occurredAt: (occurredAt ?? now).toISOString(),
    capturedAt: now.toISOString(),
    status: 'pending',
    attempts: 0,
    nextAttemptAt: 0,
  };
  await outbox.add(item);
  return item;
}
