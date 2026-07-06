// tools/code-analyzer/src/signals/event.ts
import { HunkInfo, Signal } from '../types.js';

export function extractEventHandlerSignals(hunk: HunkInfo): Signal[] {
  const signals: Signal[] = [];
  const eventPattern = /\b(on[A-Z]\w+)\s*=\s*\{/g;

  for (const line of hunk.addedLines) {
    const matches = [...line.matchAll(eventPattern)];
    for (const m of matches) {
      signals.push({ type: 'EVENT_HANDLER', detail: m[1] });
    }
  }

  return signals;
}