import { BenchmarkConfig, BenchmarkResult } from './types';
import { formatBytes, printTable, saveResults, sleep } from './utils';
import { runRabbitMQBenchmark } from './rabbitmq';
import { runRedisBenchmark } from './redis-bench';

// ─── Scenario definitions ────────────────────────────────────────────────────

const BASIC: BenchmarkConfig[] = [
  { broker: 'rabbitmq', messageSizeBytes: 1024, targetRatePerSec: 1000, durationSeconds: 20, label: 'Basic 1KB @1k/s' },
  { broker: 'redis',    messageSizeBytes: 1024, targetRatePerSec: 1000, durationSeconds: 20, label: 'Basic 1KB @1k/s' },
];

const SIZE: BenchmarkConfig[] = [128, 1024, 10240, 102400].flatMap((size) => [
  { broker: 'rabbitmq' as const, messageSizeBytes: size, targetRatePerSec: 1000, durationSeconds: 15, label: `${formatBytes(size)} @1k/s` },
  { broker: 'redis'    as const, messageSizeBytes: size, targetRatePerSec: 1000, durationSeconds: 15, label: `${formatBytes(size)} @1k/s` },
]);

const RATE: BenchmarkConfig[] = [1000, 5000, 10000, 20000, 0].flatMap((rate) => [
  { broker: 'rabbitmq' as const, messageSizeBytes: 1024, targetRatePerSec: rate, durationSeconds: 15, label: `1KB @${rate || 'MAX'}/s` },
  { broker: 'redis'    as const, messageSizeBytes: 1024, targetRatePerSec: rate, durationSeconds: 15, label: `1KB @${rate || 'MAX'}/s` },
]);

const EXPERIMENTS: Record<string, { title: string; configs: BenchmarkConfig[] }> = {
  basic: { title: 'Experiment 1 — Basic comparison (1KB, 1000/s)',         configs: BASIC },
  size:  { title: 'Experiment 2 — Message size impact (1000/s fixed)',     configs: SIZE  },
  rate:  { title: 'Experiment 3 — Rate intensity (1KB fixed)',             configs: RATE  },
};

// ─── Runner ──────────────────────────────────────────────────────────────────

async function runOne(config: BenchmarkConfig): Promise<BenchmarkResult> {
  const label = `[${config.broker.toUpperCase()}] ${config.label}`;
  console.log(`\n▶ Starting: ${label}`);
  const start = Date.now();

  const result =
    config.broker === 'rabbitmq'
      ? await runRabbitMQBenchmark(config)
      : await runRedisBenchmark(config);

  const elapsed = ((Date.now() - start) / 1000).toFixed(1);
  console.log(
    `✓ Done (${elapsed}s): recv=${result.received} lost=${result.lost} ` +
    `rate=${result.actualRatePerSec}/s avg=${result.avgLatencyMs}ms p95=${result.p95LatencyMs}ms`,
  );
  return result;
}

async function runExperiment(name: string): Promise<BenchmarkResult[]> {
  const exp = EXPERIMENTS[name];
  if (!exp) {
    console.error(`Unknown experiment: ${name}. Available: ${Object.keys(EXPERIMENTS).join(', ')}, all`);
    process.exit(1);
  }

  console.log(`\n${'═'.repeat(60)}`);
  console.log(` ${exp.title}`);
  console.log(`${'═'.repeat(60)}`);

  const results: BenchmarkResult[] = [];
  for (const cfg of exp.configs) {
    results.push(await runOne(cfg));
    await sleep(1500); // let broker settle between runs
  }

  printTable(results, exp.title);
  return results;
}

// ─── Entry point ─────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const arg = process.argv[2] ?? 'all';
  const allResults: BenchmarkResult[] = [];
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');

  if (arg === 'all') {
    for (const name of ['basic', 'size', 'rate']) {
      const results = await runExperiment(name);
      allResults.push(...results);
      await sleep(2000);
    }
    printTable(allResults, 'FULL SUMMARY');
    saveResults(allResults, `results/results-${timestamp}.json`);
  } else {
    const results = await runExperiment(arg);
    saveResults(results, `results/results-${arg}-${timestamp}.json`);
  }
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
