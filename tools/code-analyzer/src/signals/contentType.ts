// tools/code-analyzer/src/signals/contentType.ts
import { HunkInfo, Signal } from '../types.js';

/**
 * Detect file-type-related signals that don't need AST analysis:
 * - TEXT_CHANGE: constant.ts/contant.ts files with only string/object content
 * - TYPE_CHANGE: types.ts files with interface/type/enum declarations
 * - TEST_CHANGE: *.test.ts/*.spec.ts files
 */
const constantFilePattern = /\/?(constant|contant)\.ts$/;
const typeFilePattern = /\/?types\.ts$/;
const testFilePattern = /\.(test|spec)\.(ts|tsx)$/;
const typeKeywordPattern = /\b(interface|type|enum)\s+\w/;

export function extractContentTypeSignals(hunk: HunkInfo): Signal[] {
  const signals: Signal[] = [];

  for (let i = 0; i < hunk.addedLines.length; i++) {
    const line = hunk.addedLines[i];
    const hunkLine = hunk.targetLine + i;

    // TEST_CHANGE: any change in test files
    if (testFilePattern.test(hunk.file)) {
      signals.push({ type: 'TEST_CHANGE', detail: hunk.file, line: hunkLine });
      // For test files, don't add other signals — they're all test-related
      return signals;
    }

    // TEXT_CHANGE: constant files with string/object literal content
    if (constantFilePattern.test(hunk.file)) {
      const trimmed = line.trim();
      if (trimmed.startsWith("'") || trimmed.startsWith('"') || trimmed.startsWith('`') ||
          trimmed.startsWith('{') || trimmed.startsWith('[') ||
          trimmed.match(/^(export\s+)?(const|let|var)\s+\w+\s*=\s*['"{[`]/)) {
        signals.push({ type: 'TEXT_CHANGE', detail: line.trim().slice(0, 60), line: hunkLine });
        continue;
      }
    }

    // TYPE_CHANGE: types files with interface/type/enum declarations
    if (typeFilePattern.test(hunk.file) && typeKeywordPattern.test(line)) {
      signals.push({ type: 'TYPE_CHANGE', detail: line.trim().slice(0, 60), line: hunkLine });
    }
  }

  return signals;
}