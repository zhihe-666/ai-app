// tools/code-analyzer/src/snippet/extractSnippet.ts
import { HunkInfo, Snippet, DocContext } from '../types.js';

export function extractSnippet(hunk: HunkInfo, allSignals: string[]): Snippet {
  const before = hunk.removedLines.length > 0
    ? hunk.removedLines.slice(0, 50).join('\n')
    : null;
  const after = hunk.addedLines.length > 0
    ? hunk.addedLines.slice(0, 50).join('\n')
    : null;

  return {
    file: hunk.file,
    signals: allSignals.map(type => ({ type: type as any, detail: '' })),
    before,
    after,
    diffHunk: hunk.rawText.slice(0, 5000),
  };
}

export function collectDocContext(hunk: HunkInfo): DocContext {
  const jsDoc: string[] = [];
  const testDescriptions: string[] = [];
  let readme: string | null = null;

  for (const line of hunk.addedLines) {
    const jsDocMatch = line.match(/\/\*\*([^*]|\*[^/])*\*\//);
    if (jsDocMatch) {
      jsDoc.push(jsDocMatch[0]);
    }
  }

  const testMatch = hunk.file.match(/__tests__\/(.+)\.(test|spec)\./);
  if (testMatch) {
    for (const line of [...hunk.addedLines, ...hunk.removedLines]) {
      const descMatch = line.match(/(?:describe|it|test)\s*\(\s*['"`]([^'"`]+)['"`]/);
      if (descMatch) {
        testDescriptions.push(descMatch[1]);
      }
    }
  }

  return { jsDoc, testDescriptions, readme };
}