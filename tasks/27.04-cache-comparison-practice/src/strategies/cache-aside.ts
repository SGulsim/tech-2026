import { Cache } from '../cache';
import { Database } from '../db';
import { Product } from '../types';
import { CacheStrategy } from './strategy';

/**
 * Cache-Aside (Lazy Loading / Write-Around).
 *   read  : check cache → if miss, load from DB and store in cache
 *   write : write to DB only; invalidate the cache entry so next read refreshes it
 */
export class CacheAsideStrategy implements CacheStrategy {
  public readonly name = 'cache-aside';

  constructor(private cache: Cache, private db: Database) {}

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
    await this.db.upsertProduct(p);
    await this.cache.del(p.id);
  }

  async shutdown(): Promise<void> {
    /* nothing to flush */
  }
}
