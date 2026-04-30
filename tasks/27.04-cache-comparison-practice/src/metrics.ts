import { Metrics, RunResult, ScenarioName, StrategyName } from './types';

export function emptyMetrics(): Metrics {
  return {
    reads: 0,
    writes: 0,
    cacheHits: 0,
    cacheMisses: 0,
    dbReads: 0,
    dbWrites: 0,
    readLatencies: [],
    writeLatencies: [],
    errors: 0,
  };
}

export function avg(arr: number[]): number {
  if (arr.length === 0) return 0;
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

export function buildResult(
  strategy: StrategyName,
  scenario: ScenarioName,
  metrics: Metrics,
  durationMs: number,
): RunResult {
  const totalOps = metrics.reads + metrics.writes;
  const totalLat = [...metrics.readLatencies, ...metrics.writeLatencies];
  const totalCacheLookups = metrics.cacheHits + metrics.cacheMisses;
  const hitRate =
    totalCacheLookups > 0 ? metrics.cacheHits / totalCacheLookups : 0;

  return {
    strategy,
    scenario,
    totalOps,
    durationMs,
    throughput: Math.round(totalOps / (durationMs / 1000)),
    avgLatencyMs: round(avg(totalLat)),
    avgReadLatencyMs: round(avg(metrics.readLatencies)),
    avgWriteLatencyMs: round(avg(metrics.writeLatencies)),
    cacheHits: metrics.cacheHits,
    cacheMisses: metrics.cacheMisses,
    cacheHitRate: round(hitRate * 100),
    dbReads: metrics.dbReads,
    dbWrites: metrics.dbWrites,
    dbTotal: metrics.dbReads + metrics.dbWrites,
    errors: metrics.errors,
  };
}

function round(x: number): number {
  return Math.round(x * 100) / 100;
}
