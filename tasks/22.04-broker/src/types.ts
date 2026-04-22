export interface TestMessage {
  id: string;
  sentAt: number;
  payload: string;
}

export interface BenchmarkConfig {
  broker: 'rabbitmq' | 'redis';
  messageSizeBytes: number;
  targetRatePerSec: number; // 0 = unlimited (max speed)
  durationSeconds: number;
  label: string;
}

export interface Stats {
  sent: number;
  received: number;
  errors: number;
  latencies: number[];
}

export interface BenchmarkResult {
  broker: 'rabbitmq' | 'redis';
  label: string;
  messageSizeBytes: number;
  targetRatePerSec: number;
  durationSeconds: number;
  sent: number;
  received: number;
  lost: number;
  errors: number;
  actualRatePerSec: number;
  avgLatencyMs: number;
  p95LatencyMs: number;
  maxLatencyMs: number;
}
