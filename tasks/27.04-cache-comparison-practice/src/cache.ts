import Redis from 'ioredis';
import { Product } from './types';

const REDIS_URL = process.env.REDIS_URL ?? 'redis://localhost:6380';

const KEY_PREFIX = 'product:';

export class Cache {
  private client: Redis;
  public hits = 0;
  public misses = 0;

  constructor() {
    this.client = new Redis(REDIS_URL, { lazyConnect: true });
  }

  async connect(): Promise<void> {
    await this.client.connect();
  }

  async flush(): Promise<void> {
    await this.client.flushdb();
  }

  resetCounters(): void {
    this.hits = 0;
    this.misses = 0;
  }

  async get(id: number): Promise<Product | null> {
    const raw = await this.client.get(KEY_PREFIX + id);
    if (raw === null) {
      this.misses++;
      return null;
    }
    this.hits++;
    return JSON.parse(raw) as Product;
  }

  async set(p: Product): Promise<void> {
    await this.client.set(KEY_PREFIX + p.id, JSON.stringify(p));
  }

  async del(id: number): Promise<void> {
    await this.client.del(KEY_PREFIX + id);
  }

  async close(): Promise<void> {
    await this.client.quit();
  }
}
