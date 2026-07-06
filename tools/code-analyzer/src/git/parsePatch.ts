// tools/code-analyzer/src/git/parsePatch.ts
import { HunkInfo } from '../types.js';

export function parseHunks(patchContent: string, frontendPaths: string[]): HunkInfo[] {
  const hunks: HunkInfo[] = [];
  const fileHeaderRegex = /^diff --git a\/(.+?) b\/(.+?)$/m;
  const hunkHeaderRegex = /^@@ -(\d+),(\d+) \+(\d+),(\d+) @@/;

  let currentFile = '';
  let currentStatus: 'A' | 'M' | 'D' = 'M';
  let currentHunk: Partial<HunkInfo> | null = null;

  const lines = patchContent.split('\n');

  // First pass: find file headers and their positions
  const fileBoundaries: { line: number; file: string; status: 'A' | 'M' | 'D' }[] = [];
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(fileHeaderRegex);
    if (m) {
      const targetFile = m[2];
      const inScope = frontendPaths.some(p => targetFile.startsWith(p));
      if (inScope) {
        fileBoundaries.push({ line: i, file: targetFile, status: 'M' });
      }
    }
    if (lines[i].startsWith('new file mode')) {
      fileBoundaries.length > 0 && (fileBoundaries[fileBoundaries.length - 1].status = 'A');
    }
    if (lines[i].startsWith('deleted file mode')) {
      fileBoundaries.length > 0 && (fileBoundaries[fileBoundaries.length - 1].status = 'D');
    }
  }

  // Second pass: extract hunks by processing each file section
  for (let bi = 0; bi < fileBoundaries.length; bi++) {
    currentFile = fileBoundaries[bi].file;
    currentStatus = fileBoundaries[bi].status;

    const startLine = fileBoundaries[bi].line;
    const endLine = bi + 1 < fileBoundaries.length ? fileBoundaries[bi + 1].line : lines.length;

    for (let i = startLine; i < endLine; i++) {
      const hunkMatch = hunkHeaderRegex.exec(lines[i]);
      if (hunkMatch) {
        // Save previous hunk if exists
        if (currentHunk && (currentHunk.addedLines?.length || currentHunk.removedLines?.length)) {
          hunks.push(currentHunk as HunkInfo);
        }
        currentHunk = {
          file: currentFile,
          status: currentStatus,
          baseLine: parseInt(hunkMatch[1]),
          baseCount: parseInt(hunkMatch[2]),
          targetLine: parseInt(hunkMatch[3]),
          targetCount: parseInt(hunkMatch[4]),
          addedLines: [],
          removedLines: [],
          rawText: lines[i] + '\n',
        };
        continue;
      }

      if (currentHunk) {
        currentHunk.rawText = (currentHunk.rawText || '') + lines[i] + '\n';
        if (lines[i].startsWith('+') && !lines[i].startsWith('+++')) {
          currentHunk.addedLines!.push(lines[i].slice(1));
        } else if (lines[i].startsWith('-') && !lines[i].startsWith('---')) {
          currentHunk.removedLines!.push(lines[i].slice(1));
        }
      }
    }
  }

  // Push last hunk
  if (currentHunk && (currentHunk.addedLines?.length || currentHunk.removedLines?.length)) {
    hunks.push(currentHunk as HunkInfo);
  }

  return hunks;
}