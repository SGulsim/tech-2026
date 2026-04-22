import { Stats, BenchmarkConfig, BenchmarkResult } from './types';
import * as fs from 'fs';
import * as path from 'path';

export function generatePayload(sizeBytes: number): string {
  return 'x'.repeat(Math.max(1, sizeBytes));
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0;
  const idx = Math.ceil((p / 100) * sorted.length) - 1;
  return sorted[Math.max(0, Math.min(idx, sorted.length - 1))];
}

export function buildResult(
  config: BenchmarkConfig,
  stats: Stats,
  actualDurationMs: number,
): BenchmarkResult {
  const sorted = [...stats.latencies].sort((a, b) => a - b);
  const avg =
    sorted.length > 0 ? sorted.reduce((a, b) => a + b, 0) / sorted.length : 0;

  return {
    broker: config.broker,
    label: config.label,
    messageSizeBytes: config.messageSizeBytes,
    targetRatePerSec: config.targetRatePerSec,
    durationSeconds: config.durationSeconds,
    sent: stats.sent,
    received: stats.received,
    lost: Math.max(0, stats.sent - stats.received),
    errors: stats.errors,
    actualRatePerSec: Math.round(stats.received / (actualDurationMs / 1000)),
    avgLatencyMs: Math.round(avg * 10) / 10,
    p95LatencyMs: percentile(sorted, 95),
    maxLatencyMs: sorted[sorted.length - 1] ?? 0,
  };
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

export function printTable(results: BenchmarkResult[], title: string): void {
  const W = 130;
  console.log('\n' + '='.repeat(W));
  console.log(` ${title}`);
  console.log('='.repeat(W));

  const header = [
    'Broker'.padEnd(9),
    'Label'.padEnd(30),
    'Size'.padStart(7),
    'Target/s'.padStart(9),
    'Sent'.padStart(8),
    'Recv'.padStart(8),
    'Lost'.padStart(6),
    'Err'.padStart(5),
    'Act/s'.padStart(7),
    'Avg ms'.padStart(8),
    'p95 ms'.padStart(8),
    'Max ms'.padStart(8),
  ].join(' ');

  console.log(header);
  console.log('-'.repeat(W));

  for (const r of results) {
    const row = [
      r.broker.padEnd(9),
      r.label.substring(0, 30).padEnd(30),
      formatBytes(r.messageSizeBytes).padStart(7),
      (r.targetRatePerSec === 0 ? 'MAX' : r.targetRatePerSec.toString()).padStart(9),
      r.sent.toString().padStart(8),
      r.received.toString().padStart(8),
      r.lost.toString().padStart(6),
      r.errors.toString().padStart(5),
      r.actualRatePerSec.toString().padStart(7),
      r.avgLatencyMs.toFixed(1).padStart(8),
      r.p95LatencyMs.toString().padStart(8),
      r.maxLatencyMs.toString().padStart(8),
    ].join(' ');
    console.log(row);
  }

  console.log('='.repeat(W));
}

export function saveResults(results: BenchmarkResult[], filePath: string): void {
  const dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(results, null, 2), 'utf-8');
  console.log(`\nResults saved → ${filePath}`);
}
