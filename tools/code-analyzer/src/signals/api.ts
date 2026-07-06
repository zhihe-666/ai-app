// tools/code-analyzer/src/signals/api.ts
import { HunkInfo, Signal } from '../types.js';

export function extractApiSignals(hunk: HunkInfo): Signal[] {
  const signals: Signal[] = [];

  const apiPatterns = [
    /\b(?:api|request|client|http)\s*\.\s*(?:get|post|put|patch|delete|request)\s*\(/,
    /\bfetch\s*\(/,
    /\baxios\s*\.\s*(?:get|post|put|delete)\s*\(/,
    /\buseRequest\s*\(/,
  ];

  for (const line of hunk.addedLines) {
    for (const pattern of apiPatterns) {
      if (pattern.test(line)) {
        const trimmed = line.trim().slice(0, 80);
        signals.push({ type: 'API_CALL', detail: trimmed });
        break;
      }
    }
  }

  return signals;
}