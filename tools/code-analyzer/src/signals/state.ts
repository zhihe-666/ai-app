// tools/code-analyzer/src/signals/state.ts
import { HunkInfo, Signal } from '../types.js';

export function extractStateSignals(hunk: HunkInfo): Signal[] {
  const signals: Signal[] = [];

  const statePatterns = [
    /\bset\w+\s*\(/,           // useState setters
    /\bdispatch\s*\(/,         // Redux dispatch
    /\bcommit\s*\(/,           // Vuex / Pinia commit
    /\buseState\s*\(/,         // useState calls
    /\buseReducer\s*\(/,       // useReducer calls
    /\bdefineStore\s*\(/,      // Pinia store definition
  ];

  for (const line of hunk.addedLines) {
    for (const pattern of statePatterns) {
      if (pattern.test(line)) {
        const trimmed = line.trim().slice(0, 60);
        signals.push({ type: 'STATE_ACTION', detail: trimmed });
        break;
      }
    }
  }

  return signals;
}