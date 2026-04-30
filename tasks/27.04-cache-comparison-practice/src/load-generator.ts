import { Product, Scenario } from './types';
import { CacheStrategy } from './strategies/strategy';

export type Operation = { kind: 'read' | 'write'; id: number };

/**
 * Build a deterministic operation sequence for a given scenario.
 * Using a seeded PRNG so every strategy replays exactly the same workload.
 */
export function buildOpSequence(
  scenario: Scenario,
  datasetSize: number,
  seed = 42,
): Operation[] {
  const rng = mulberry32(seed);
  const ops: Operation[] = [];
  for (let i = 0; i < scenario.totalOps; i++) {
    const isRead = rng() < scenario.readRatio;
    const id = 1 + Math.floor(rng() * datasetSize);
    ops.push({ kind: isRead ? 'read' : 'write', id });
  }
  return ops;
}

export type RunStats = {
  reads: number;
  writes: number;
  readLatencies: number[];
  writeLatencies: number[];
  errors: number;
};

/**
 * Replay an operation sequence against a strategy with a fixed concurrency level.
 * Returns wall-clock duration and per-op latencies.
 */
export async function runWorkload(
  strategy: CacheStrategy,
  ops: Operation[],
  concurrency: number,
): Promise<{ stats: RunStats; durationMs: number }> {
  const stats: RunStats = {
    reads: 0,
    writes: 0,
    readLatencies: [],
    writeLatencies: [],
    errors: 0,
  };

  let cursor = 0;
  const t0 = Date.now();

  async function worker(): Promise<void> {
    while (true) {
      const idx = cursor++;
      if (idx >= ops.length) break;
      const op = ops[idx];

      const t = Date.now();
      try {
        if (op.kind === 'read') {
          await strategy.get(op.id);
          stats.readLatencies.push(Date.now() - t);
          stats.reads++;
        } else {
          const product: Product = {
            id: op.id,
            name: `product-${op.id}`,
            price: 100 + (op.id % 1000) + (idx % 7) * 0.5,
          };
          await strategy.set(product);
          stats.writeLatencies.push(Date.now() - t);
          stats.writes++;
        }
      } catch (err) {
        stats.errors++;
        if (stats.errors < 3) console.error('worker error:', err);
      }
    }
  }

  await Promise.all(Array.from({ length: concurrency }, () => worker()));

  return { stats, durationMs: Date.now() - t0 };
}

// Tiny seeded PRNG (Mulberry32) — deterministic across Node versions.
function mulberry32(seed: number): () => number {
  let a = seed | 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
