import { Pool } from 'pg';
import { Product } from './types';

const PG_URL =
  process.env.PG_URL ?? 'postgres://app:app@localhost:5433/shop';

export class Database {
  private pool: Pool;
  public reads = 0;
  public writes = 0;

  constructor() {
    this.pool = new Pool({ connectionString: PG_URL, max: 20 });
  }

  async init(): Promise<void> {
    await this.pool.query(`
      CREATE TABLE IF NOT EXISTS products (
        id    INTEGER PRIMARY KEY,
        name  TEXT    NOT NULL,
        price NUMERIC NOT NULL
      )
    `);
  }

  async seed(count: number): Promise<void> {
    await this.pool.query('TRUNCATE products');
    const values: string[] = [];
    const params: unknown[] = [];
    for (let i = 1; i <= count; i++) {
      const base = (i - 1) * 3;
      values.push(`($${base + 1}, $${base + 2}, $${base + 3})`);
      params.push(i, `product-${i}`, 100 + (i % 1000));
    }
    await this.pool.query(
      `INSERT INTO products (id, name, price) VALUES ${values.join(',')}`,
      params,
    );
  }

  resetCounters(): void {
    this.reads = 0;
    this.writes = 0;
  }

  async getProduct(id: number): Promise<Product | null> {
    this.reads++;
    const res = await this.pool.query(
      'SELECT id, name, price FROM products WHERE id = $1',
      [id],
    );
    if (res.rowCount === 0) return null;
    const row = res.rows[0];
    return { id: row.id, name: row.name, price: Number(row.price) };
  }

  async upsertProduct(p: Product): Promise<void> {
    this.writes++;
    await this.pool.query(
      `INSERT INTO products (id, name, price) VALUES ($1, $2, $3)
       ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, price = EXCLUDED.price`,
      [p.id, p.name, p.price],
    );
  }

  async upsertBatch(items: Product[]): Promise<void> {
    if (items.length === 0) return;
    this.writes += items.length;
    const values: string[] = [];
    const params: unknown[] = [];
    items.forEach((p, idx) => {
      const base = idx * 3;
      values.push(`($${base + 1}, $${base + 2}, $${base + 3})`);
      params.push(p.id, p.name, p.price);
    });
    await this.pool.query(
      `INSERT INTO products (id, name, price) VALUES ${values.join(',')}
       ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, price = EXCLUDED.price`,
      params,
    );
  }

  async close(): Promise<void> {
    await this.pool.end();
  }
}
