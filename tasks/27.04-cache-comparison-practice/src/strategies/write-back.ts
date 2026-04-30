import { Cache } from '../cache';
import { Database } from '../db';
import { Product } from '../types';
import { CacheStrategy } from './strategy';

export type WriteBackOptions = {
  flushIntervalMs: number; // how often the background flusher runs
  flushBatchSize: number;  // max items per DB batch upsert
};

/**
 * Write-Back (Write-Behind).
 *   read  : check cache → if miss, load from DB and store in cache
 *   write : write to cache + put into in-memory dirty buffer
 *           background flusher periodically pushes the buffer into DB
 */
export class WriteBackStrategy implements CacheStrategy {
  public readonly name = 'write-back';

  private dirty = new Map<number, Product>();
  private timer: NodeJS.Timeout | null = null;
  private flushing = false;

  constructor(
    private cache: Cache,
    private db: Database,
    private opts: WriteBackOptions = { flushIntervalMs: 1000, flushBatchSize: 200 },
  ) {}

  start(): void {
    if (this.timer) return;
    this.timer = setInterval(() => {
      this.flushOnce().catch((err) => {
        console.error('[write-back] flush error:', err);
      });
    }, this.opts.flushIntervalMs);
  }

  bufferSize(): number {
    return this.dirty.size;
  }

  async get(id: number): Promise<Product | null> {
    const cached = await this.cache.get(id);
    if (cached !== null) return cached;

    const fromDb = await this.db.getProduct(id);
    if (fromDb !== null) {
      await this.cache.set(fromDb);
    }
    return fromDb;
  }

  async set(p: Product): Promise<void> {
    await this.cache.set(p);
    // overwrite previous dirty version (write-coalescing: multiple writes to same id
    // collapse into one DB upsert when flushed)
    this.dirty.set(p.id, p);
  }

  async flushOnce(): Promise<void> {
    if (this.flushing) return;
    if (this.dirty.size === 0) return;
    this.flushing = true;
    try {
      // snapshot current dirty entries and clear the live buffer so new writes can keep coming
      const snapshot = Array.from(this.dirty.values());
      this.dirty.clear();

      for (let i = 0; i < snapshot.length; i += this.opts.flushBatchSize) {
        const batch = snapshot.slice(i, i + this.opts.flushBatchSize);
        await this.db.upsertBatch(batch);
      }
    } finally {
      this.flushing = false;
    }
  }

  async shutdown(): Promise<void> {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    // Drain remaining dirty entries before closing
    while (this.dirty.size > 0 || this.flushing) {
      await this.flushOnce();
      if (this.flushing) {
        await new Promise((r) => setTimeout(r, 20));
      }
    }
  }
}
