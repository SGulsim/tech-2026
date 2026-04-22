import Redis from 'ioredis';
import { randomUUID } from 'crypto';
import { BenchmarkConfig, BenchmarkResult, Stats, TestMessage } from './types';
import { buildResult, generatePayload, sleep } from './utils';

const REDIS_URL = process.env.REDIS_URL ?? 'redis://localhost:6379';
const STREAM = 'benchmark-stream';
const GROUP = 'benchmark-group';
const CONSUMER = 'consumer-1';

const BATCH_INTERVAL_MS = 50;
const BATCHES_PER_SEC = 1000 / BATCH_INTERVAL_MS;

type XReadGroupResult = Array<[string, Array<[string, string[]]>]> | null;

export async function runRedisBenchmark(
  config: BenchmarkConfig,
): Promise<BenchmarkResult> {
  const producer = new Redis(REDIS_URL, { lazyConnect: true });
  const consumer = new Redis(REDIS_URL, { lazyConnect: true });
  await producer.connect();
  await consumer.connect();

  // Reset stream
  await producer.del(STREAM);
  try {
    await producer.xgroup('CREATE', STREAM, GROUP, '$', 'MKSTREAM');
  } catch (err: unknown) {
    if (!(err instanceof Error && err.message.includes('BUSYGROUP'))) throw err;
  }

  const stats: Stats = { sent: 0, received: 0, errors: 0, latencies: [] };
  let stopped = false;

  async function consumerLoop(): Promise<void> {
    while (!stopped) {
      try {
        const result = (await consumer.xreadgroup(
          'GROUP',
          GROUP,
          CONSUMER,
          'COUNT',
          '200',
          'BLOCK',
          '100',
          'STREAMS',
          STREAM,
          '>',
        )) as XReadGroupResult;

        if (!result) continue;

        for (const [, messages] of result) {
          const ids: string[] = [];
          for (const [id, fields] of messages) {
            // fields = [key1, val1, key2, val2, ...]
            const map: Record<string, string> = {};
            for (let i = 0; i < fields.length - 1; i += 2) {
              map[fields[i]] = fields[i + 1];
            }
            try {
              const data = JSON.parse(map['data']) as TestMessage;
              stats.latencies.push(Date.now() - data.sentAt);
              stats.received++;
            } catch {
              stats.errors++;
            }
            ids.push(id);
          }
          if (ids.length > 0) {
            await consumer.xack(STREAM, GROUP, ...ids);
          }
        }
      } catch {
        if (!stopped) await sleep(10);
      }
    }
  }

  const consumerPromise = consumerLoop();

  const payload = generatePayload(config.messageSizeBytes);
  const msgsPerBatch =
    config.targetRatePerSec === 0
      ? 500
      : Math.max(1, Math.round(config.targetRatePerSec / BATCHES_PER_SEC));

  const startTime = Date.now();
  const endTime = startTime + config.durationSeconds * 1000;

  while (Date.now() < endTime) {
    const batchStart = Date.now();
    const pipeline = producer.pipeline();
    const count = Math.min(msgsPerBatch, 500);

    for (let i = 0; i < count; i++) {
      if (Date.now() >= endTime) break;
      const msg: TestMessage = { id: randomUUID(), sentAt: Date.now(), payload };
      pipeline.xadd(STREAM, '*', 'data', JSON.stringify(msg));
      stats.sent++;
    }

    try {
      await pipeline.exec();
    } catch {
      stats.errors += count;
      stats.sent -= count;
    }

    if (config.targetRatePerSec > 0) {
      const wait = BATCH_INTERVAL_MS - (Date.now() - batchStart);
      if (wait > 0) await sleep(wait);
    }
  }

  const producerEndTime = Date.now();
  const producerDurationMs = producerEndTime - startTime;

  const gracePeriodMs = Math.min(5000, config.durationSeconds * 300);
  process.stdout.write(
    `  [Redis] sent=${stats.sent}, waiting ${gracePeriodMs}ms for consumer...\n`,
  );
  await sleep(gracePeriodMs);

  stopped = true;
  // Disconnect to unblock the BLOCK call in consumerLoop
  await consumer.quit();
  await consumerPromise.catch(() => {});
  await producer.quit();

  return buildResult(config, stats, producerDurationMs);
}
