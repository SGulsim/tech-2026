import { Cache } from './cache';
import { Database } from './db';
import { WriteBackStrategy } from './strategies/write-back';
import { Product } from './types';

/**
 * Stand-alone demo for Write-Back: shows what happens to the dirty buffer
 * while writes are streaming in faster than the flusher drains them.
 */

const DATASET_SIZE = 200;
const TOTAL_WRITES = 60000;
const UNIQUE_KEYS = 60000;        // each write goes to a unique id → no coalescing → buffer really grows
const CONCURRENCY = 50;
const FLUSH_INTERVAL_MS = 1000;   // background flusher tick
const FLUSH_BATCH_SIZE = 500;
const SAMPLE_INTERVAL_MS = 100;

async function main(): Promise<void> {
  const db = new Database();
  await db.init();
  await db.seed(DATASET_SIZE);
  db.resetCounters();

  const cache = new Cache();
  await cache.connect();
  await cache.flush();
  cache.resetCounters();

  const strategy = new WriteBackStrategy(cache, db, {
    flushIntervalMs: FLUSH_INTERVAL_MS,
    flushBatchSize: FLUSH_BATCH_SIZE,
  });
  strategy.start();

  console.log('═'.repeat(70));
  console.log(' WRITE-BACK BUFFER ACCUMULATION DEMO');
  console.log('═'.repeat(70));
  console.log(
    ` writes=${TOTAL_WRITES}, concurrency=${CONCURRENCY}, ` +
    `flushInterval=${FLUSH_INTERVAL_MS}ms, batchSize=${FLUSH_BATCH_SIZE}`,
  );
  console.log('-'.repeat(70));
  console.log(' time(ms)   buffer   db_writes   note');
  console.log('-'.repeat(70));

  let maxBuffer = 0;
  const t0 = Date.now();
  const samples: Array<{ t: number; buffer: number; dbWrites: number }> = [];

  const sampler = setInterval(() => {
    const t = Date.now() - t0;
    const buffer = strategy.bufferSize();
    if (buffer > maxBuffer) maxBuffer = buffer;
    samples.push({ t, buffer, dbWrites: db.writes });
    console.log(
      ` ${t.toString().padStart(8)}   ` +
      `${buffer.toString().padStart(6)}   ` +
      `${db.writes.toString().padStart(9)}`,
    );
  }, SAMPLE_INTERVAL_MS);

  // Writer workers — pushes writes to the strategy as fast as they go
  let issued = 0;
  async function writer(): Promise<void> {
    while (true) {
      const i = issued++;
      if (i >= TOTAL_WRITES) break;
      // Use a unique id per write so the dirty buffer cannot coalesce —
      // this makes the accumulation effect visible
      const id = 1 + (i % UNIQUE_KEYS);
      const p: Product = { id, name: `product-${id}`, price: 100 + (i % 1000) };
      await strategy.set(p);
    }
  }
  const writeStart = Date.now();
  await Promise.all(Array.from({ length: CONCURRENCY }, () => writer()));
  const writeEnd = Date.now();

  console.log('-'.repeat(70));
  console.log(
    ` writes finished in ${writeEnd - writeStart}ms — ` +
    `now waiting for buffer to drain on shutdown...`,
  );
  console.log('-'.repeat(70));

  await strategy.shutdown(); // drains remaining buffer
  clearInterval(sampler);

  const finalT = Date.now() - t0;
  console.log(' ' + finalT.toString().padStart(8) +
    `        0   ${db.writes.toString().padStart(9)}   shutdown drain complete`);
  console.log('-'.repeat(70));
  console.log(' RESULTS');
  console.log('-'.repeat(70));
  console.log(`  total writes issued by app:  ${TOTAL_WRITES}`);
  console.log(`  unique keys in dataset:      ${DATASET_SIZE}`);
  console.log(`  max buffer size observed:    ${maxBuffer}`);
  console.log(`  total DB writes (rows):      ${db.writes}`);
  console.log(`  write coalescing factor:     ${(TOTAL_WRITES / db.writes).toFixed(2)}× ` +
    `(${TOTAL_WRITES} app writes → ${db.writes} DB rows)`);
  console.log(`  total wall time:             ${finalT}ms`);
  console.log('═'.repeat(70));

  await cache.close();
  await db.close();
}

main().catch((err) => {
  console.error('Fatal:', err);
  process.exit(1);
});
