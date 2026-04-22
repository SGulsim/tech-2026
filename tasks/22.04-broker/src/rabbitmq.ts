import * as amqp from 'amqplib';
import { randomUUID } from 'crypto';
import { BenchmarkConfig, BenchmarkResult, Stats, TestMessage } from './types';
import { buildResult, generatePayload, sleep } from './utils';

const RABBITMQ_URL = process.env.RABBITMQ_URL ?? 'amqp://guest:guest@localhost:5672';
const QUEUE = 'benchmark';

// Batch size per 50ms window for rate control
const BATCH_INTERVAL_MS = 50;
const BATCHES_PER_SEC = 1000 / BATCH_INTERVAL_MS; // 20

export async function runRabbitMQBenchmark(
  config: BenchmarkConfig,
): Promise<BenchmarkResult> {
  const conn = await amqp.connect(RABBITMQ_URL);

  const producerCh = await conn.createChannel();
  const consumerCh = await conn.createChannel();

  await producerCh.assertQueue(QUEUE, { durable: false });
  await producerCh.purgeQueue(QUEUE);
  // Don't overwhelm consumer in-memory buffer
  await consumerCh.prefetch(200);

  const stats: Stats = { sent: 0, received: 0, errors: 0, latencies: [] };

  await consumerCh.consume(QUEUE, (msg) => {
    if (!msg) return;
    try {
      const data = JSON.parse(msg.content.toString()) as TestMessage;
      stats.latencies.push(Date.now() - data.sentAt);
      stats.received++;
      consumerCh.ack(msg);
    } catch {
      consumerCh.nack(msg, false, false);
      stats.errors++;
    }
  });

  const payload = generatePayload(config.messageSizeBytes);
  const msgsPerBatch =
    config.targetRatePerSec === 0
      ? 500 // unlimited: ~10k/s max
      : Math.max(1, Math.round(config.targetRatePerSec / BATCHES_PER_SEC));

  const startTime = Date.now();
  const endTime = startTime + config.durationSeconds * 1000;

  while (Date.now() < endTime) {
    const batchStart = Date.now();

    for (let i = 0; i < msgsPerBatch; i++) {
      if (Date.now() >= endTime) break;
      const msg: TestMessage = { id: randomUUID(), sentAt: Date.now(), payload };
      try {
        const ok = producerCh.sendToQueue(QUEUE, Buffer.from(JSON.stringify(msg)));
        if (ok) {
          stats.sent++;
        } else {
          // Channel write buffer full - brief pause and retry once
          await sleep(5);
          producerCh.sendToQueue(QUEUE, Buffer.from(JSON.stringify(msg)));
          stats.sent++;
        }
      } catch {
        stats.errors++;
      }
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
    `  [RabbitMQ] sent=${stats.sent}, waiting ${gracePeriodMs}ms for consumer...\n`,
  );
  await sleep(gracePeriodMs);

  await conn.close();

  return buildResult(config, stats, producerDurationMs);
}
