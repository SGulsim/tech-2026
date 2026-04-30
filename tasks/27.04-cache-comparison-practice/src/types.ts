export type Product = {
  id: number;
  name: string;
  price: number;
};

export type StrategyName = 'cache-aside' | 'write-through' | 'write-back';

export type ScenarioName = 'read-heavy' | 'balanced' | 'write-heavy';

export type Scenario = {
  name: ScenarioName;
  readRatio: number;
  totalOps: number;
  concurrency: number;
};

export type Metrics = {
  reads: number;
  writes: number;
  cacheHits: number;
  cacheMisses: number;
  dbReads: number;
  dbWrites: number;
  readLatencies: number[];
  writeLatencies: number[];
  errors: number;
};

export type RunResult = {
  strategy: StrategyName;
  scenario: ScenarioName;
  totalOps: number;
  durationMs: number;
  throughput: number;
  avgLatencyMs: number;
  avgReadLatencyMs: number;
  avgWriteLatencyMs: number;
  cacheHits: number;
  cacheMisses: number;
  cacheHitRate: number;
  dbReads: number;
  dbWrites: number;
  dbTotal: number;
  errors: number;
};
