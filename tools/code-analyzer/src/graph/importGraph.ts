// tools/code-analyzer/src/graph/importGraph.ts
import { HunkInfo } from '../types.js';

export interface ImportGraph {
  adjacency: Map<string, Set<string>>;
}

export function buildImportGraph(hunks: HunkInfo[], frontendPaths: string[]): ImportGraph {
  const adjacency = new Map<string, Set<string>>();
  const changedFiles = new Set(hunks.map(h => h.file));

  const fileImports = new Map<string, string[]>();
  for (const hunk of hunks) {
    const imports: string[] = [];
    for (const line of hunk.addedLines) {
      // Static import: extract module path from "from '...'"
      const staticImport = line.match(/from\s+['"`]([^'"`]+)['"`]/);
      if (staticImport) {
        imports.push(staticImport[1]);
      }
      // Dynamic import
      const dynamicImport = line.match(/import\(['"`]([^'"`]+)['"`]\)/);
      if (dynamicImport) {
        imports.push(dynamicImport[1]);
      }
    }
    fileImports.set(hunk.file, imports);
  }

  for (const [file, imports] of fileImports) {
    const neighbors = new Set<string>();
    for (const imp of imports) {
      for (const cf of changedFiles) {
        if (cf === file) continue;
        const cfBase = cf.replace(/\.(tsx?|jsx?)$/, '');
        const impBase = imp.replace(/['";]$/, '').replace(/^@\//, 'src/');
        if (cfBase.endsWith(impBase) || cfBase.includes(impBase)) {
          neighbors.add(cf);
        }
      }
    }
    adjacency.set(file, neighbors);
  }

  return { adjacency };
}