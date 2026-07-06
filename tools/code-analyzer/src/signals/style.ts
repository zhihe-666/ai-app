// tools/code-analyzer/src/signals/style.ts
import { HunkInfo, Signal } from '../types.js';

const styleExtensions = new Set(['.css', '.scss', '.less', '.sass', '.styl']);

const styleKeywords = new Set([
  'className', 'style', 'classes', 'cx', 'clsx', 'classnames',
  'styled', 'css', 'sx', 'theme', 'styles', 'makeStyles',
]);

export function extractStyleSignals(hunk: HunkInfo): Signal[] {
  const ext = hunk.file.split('.').pop()?.toLowerCase();

  // Pure style files
  if (ext && styleExtensions.has('.' + ext)) {
    return [{ type: 'STYLE_ONLY', detail: hunk.file }];
  }

  // Style purity validation for non-style files
  const nonStyleLines = hunk.addedLines.filter(line => {
    const trimmed = line.trim();
    if (!trimmed) return false;
    if (/\b(if|else|for|while|return|switch|case|import\s+\w|export\s+\w)\b/.test(trimmed)) return true;
    if (/\w+\s*\(/.test(trimmed)) {
      const callMatch = trimmed.match(/(\w+)\s*\(/);
      if (callMatch && !styleKeywords.has(callMatch[1])) return true;
    }
    if (/\b(on[A-Z]|handle\w+)\s*=\s*\{/.test(trimmed)) return true;
    return false;
  });

  if (nonStyleLines.length === 0 && hunk.addedLines.length > 0) {
    return [{ type: 'STYLE_ONLY', detail: hunk.file }];
  }

  return [];
}