import { Cache } from '../cache';
import { Database } from '../db';
import { Product } from '../types';
import { CacheStrategy } from './strategy';

/**
 * Write-Through.
 *   read  : check cache → if miss, load from DB and store in cache
 *   write : synchronously update both cache AND database in one operation
 */
export class WriteThroughStrategy implements CacheStrategy {
  public readonly name = 'write-through';

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
    await this.cache.set(p);
  }

  async shutdown(): Promise<void> {
    /* nothing to flush */
  }
}
