import * as fs from 'fs';
import * as path from 'path';

import { Cache } from './cache';
import { Database } from './db';
import { buildOpSequence, runWorkload } from './load-generator';
import { buildResult } from './metrics';
import { CacheAsideStrategy } from './strategies/cache-aside';
import { CacheStrategy } from './strategies/strategy';
import { WriteBackStrategy } from './strategies/write-back';
import { WriteThroughStrategy } from './strategies/write-through';
import { Metrics, RunResult, Scenario, StrategyName } from './types';

// ─── Test parameters (one set, applied to every strategy/scenario) ──────────

const DATASET_SIZE = 200;
const TOTAL_OPS = 10000;
const CONCURRENCY = 50;

const SCENARIOS: Scenario[] = [
  { name: 'read-heavy',  readRatio: 0.8, totalOps: TOTAL_OPS, concurrency: CONCURRENCY },
  { name: 'balanced',    readRatio: 0.5, totalOps: TOTAL_OPS, concurrency: CONCURRENCY },
  { name: 'write-heavy', readRatio: 0.2, totalOps: TOTAL_OPS, concurrency: CONCURRENCY },
];

const STRATEGIES: StrategyName[] = ['cache-aside', 'write-through', 'write-back'];

function buildStrategy(name: StrategyName, cache: Cache, db: Database): CacheStrategy {
  switch (name) {
    case 'cache-aside':   return new CacheAsideStrategy(cache, db);
    case 'write-through': return new WriteThroughStrategy(cache, db);
    case 'write-back': {
      const s = new WriteBackStrategy(cache, db, { flushIntervalMs: 1000, flushBatchSize: 200 });
      s.start();
      return s;
    }
  }
}

// ─── Main runner ────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const db = new Database();
  await db.init();

  const cache = new Cache();
  await cache.connect();

  const results: RunResult[] = [];

  for (const strategyName of STRATEGIES) {
    for (const scenario of SCENARIOS) {
      console.log(
        `\n▶ ${strategyName.toUpperCase()} | ${scenario.name} ` +
        `(${Math.round(scenario.readRatio * 100)}% read / ` +
        `${Math.round((1 - scenario.readRatio) * 100)}% write, ${scenario.totalOps} ops)`,
      );

      // Reset everything for a fair start
      await db.seed(DATASET_SIZE);
      await cache.flush();
      cache.resetCounters();
      db.resetCounters();

      const strategy = buildStrategy(strategyName, cache, db);
      const ops = buildOpSequence(scenario, DATASET_SIZE);

      const { stats, durationMs } = await runWorkload(strategy, ops, scenario.concurrency);
      await strategy.shutdown(); // for write-back: drain dirty buffer to DB

      const metrics: Metrics = {
        reads: stats.reads,
        writes: stats.writes,
        cacheHits: cache.hits,
        cacheMisses: cache.misses,
        dbReads: db.reads,
        dbWrites: db.writes,
        readLatencies: stats.readLatencies,
        writeLatencies: stats.writeLatencies,
        errors: stats.errors,
      };

      const result = buildResult(strategyName, scenario.name, metrics, durationMs);
      results.push(result);

      console.log(
        `  duration=${durationMs}ms  thr=${result.throughput} req/s  ` +
        `avg=${result.avgLatencyMs}ms  ` +
        `hit_rate=${result.cacheHitRate}%  ` +
        `db_reads=${result.dbReads}  db_writes=${result.dbWrites}  errors=${result.errors}`,
      );
    }
  }

  printTable(results);
  saveResults(results);

  await cache.close();
  await db.close();
}

function printTable(results: RunResult[]): void {
  const W = 130;
  console.log('\n' + '='.repeat(W));
  console.log(' SUMMARY — all strategies × all scenarios');
  console.log('='.repeat(W));

  const header = [
    'Strategy'.padEnd(15),
    'Scenario'.padEnd(13),
    'Ops'.padStart(7),
    'Dur(ms)'.padStart(8),
    'Thr(rps)'.padStart(9),
    'Avg(ms)'.padStart(8),
    'R-avg'.padStart(7),
    'W-avg'.padStart(7),
    'Hit%'.padStart(6),
    'DB-R'.padStart(7),
    'DB-W'.padStart(7),
    'DB-tot'.padStart(7),
    'Err'.padStart(5),
  ].join(' ');
  console.log(header);
  console.log('-'.repeat(W));

  for (const r of results) {
    console.log(
      [
        r.strategy.padEnd(15),
        r.scenario.padEnd(13),
        r.totalOps.toString().padStart(7),
        r.durationMs.toString().padStart(8),
        r.throughput.toString().padStart(9),
        r.avgLatencyMs.toFixed(2).padStart(8),
        r.avgReadLatencyMs.toFixed(2).padStart(7),
        r.avgWriteLatencyMs.toFixed(2).padStart(7),
        r.cacheHitRate.toFixed(1).padStart(6),
        r.dbReads.toString().padStart(7),
        r.dbWrites.toString().padStart(7),
        r.dbTotal.toString().padStart(7),
        r.errors.toString().padStart(5),
      ].join(' '),
    );
  }
  console.log('='.repeat(W));
}

function saveResults(results: RunResult[]): void {
  const dir = path.join(process.cwd(), 'results');
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  const ts = new Date().toISOString().replace(/[:.]/g, '-');
  const file = path.join(dir, `results-${ts}.json`);
  fs.writeFileSync(file, JSON.stringify(results, null, 2), 'utf-8');
  console.log(`\nResults saved → ${file}`);
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
