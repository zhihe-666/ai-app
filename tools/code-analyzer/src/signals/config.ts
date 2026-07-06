// tools/code-analyzer/src/signals/config.ts
import { HunkInfo, Signal } from '../types.js';

const configFilePatterns = [
  /\.env/,
  /vite\.config/,
  /\.umirc\./,
  /config\/config\.ts/,
  /webpack\.config/,
  /next\.config/,
];

export function extractConfigSignals(hunk: HunkInfo): Signal[] {
  const isConfig = configFilePatterns.some(p => p.test(hunk.file));
  if (!isConfig) return [];

  return [{ type: 'CONFIG_CHANGE', detail: hunk.file }];
}