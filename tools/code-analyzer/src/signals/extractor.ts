// tools/code-analyzer/src/signals/extractor.ts
import { Project } from 'ts-morph';
import { HunkInfo, Signal } from '../types.js';
import { extractRouteSignals } from './routes.js';
import { extractApiSignals } from './api.js';
import { extractStateSignals } from './state.js';
import { extractPermissionSignals } from './permission.js';
import { extractHookSignals } from './hooks.js';
import { extractEventHandlerSignals } from './event.js';
import { extractDataModelSignals } from './dataModel.js';
import { extractConfigSignals } from './config.js';
import { extractStyleSignals } from './style.js';
import { extractContentTypeSignals } from './contentType.js';
import { validateSignals } from './astValidator.js';

export function extractSignals(hunk: HunkInfo, frontendPaths: string[], project?: Project): Signal[] {
  let signals: Signal[] = [
    ...extractRouteSignals(hunk),
    ...extractApiSignals(hunk),
    ...extractStateSignals(hunk),
    ...extractPermissionSignals(hunk),
    ...extractHookSignals(hunk),
    ...extractEventHandlerSignals(hunk),
    ...extractDataModelSignals(hunk),
    ...extractConfigSignals(hunk),
    ...extractStyleSignals(hunk),
    ...extractContentTypeSignals(hunk),
  ];

  // Attach line numbers to signals that don't have them yet
  // Match signal.detail against addedLines to find the source line
  for (const sig of signals) {
    if (sig.line !== undefined) continue; // already has line number
    if (!sig.detail) continue;
    const detailPrefix = sig.detail.slice(0, 30); // match first 30 chars
    for (let i = 0; i < hunk.addedLines.length; i++) {
      if (hunk.addedLines[i].trim().includes(detailPrefix)) {
        sig.line = hunk.targetLine + i;
        break;
      }
    }
  }

  // Central AST validation: filter false positives that regex can't catch alone
  if (project) {
    signals = validateSignals(signals, hunk, project);
  }

  return signals;
}