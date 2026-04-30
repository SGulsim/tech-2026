import { Product } from '../types';

export interface CacheStrategy {
  name: string;
  get(id: number): Promise<Product | null>;
  set(p: Product): Promise<void>;
  shutdown(): Promise<void>;
}
