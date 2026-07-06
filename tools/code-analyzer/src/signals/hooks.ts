// tools/code-analyzer/src/signals/hooks.ts
import { HunkInfo, Signal } from '../types.js';

export function extractHookSignals(hunk: HunkInfo): Signal[] {
  const signals: Signal[] = [];
  const hookDefPattern = /(?:^|\n)\s*(?:export\s+)?(?:function\s+|const\s+)?(use[A-Z]\w+)\s*(?:=|\(|:)/;

  for (const line of hunk.addedLines) {
    const match = line.match(hookDefPattern);
    if (match) {
      signals.push({ type: 'HOOK_DEF', detail: match[1] });
    }
  }

  return signals;
}