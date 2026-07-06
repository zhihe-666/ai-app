// tools/code-analyzer/src/signals/dataModel.ts
import { HunkInfo, Signal } from '../types.js';

export function extractDataModelSignals(hunk: HunkInfo): Signal[] {
  const signals: Signal[] = [];
  const modelPatterns = [
    /\binterface\s+\w+/,
    /\btype\s+\w+\s*=/,
    /\benum\s+\w+/,
  ];

  for (const line of hunk.addedLines) {
    for (const pattern of modelPatterns) {
      if (pattern.test(line)) {
        signals.push({ type: 'DATA_MODEL', detail: line.trim() });
        break;
      }
    }
  }

  return signals;
}