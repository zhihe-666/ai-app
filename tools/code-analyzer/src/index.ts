// tools/code-analyzer/src/index.ts
import fs from 'fs';
import path from 'path';
import { Project } from 'ts-morph';
import { CliArgs, AnalysisResult, FeatureGroup, FileAnalysisResult } from './types.js';
import { parseHunks } from './git/parsePatch.js';
import { extractSignals } from './signals/extractor.js';
import { classifyGroup } from './classify/decisionTree.js';
import { extractSnippet, collectDocContext } from './snippet/extractSnippet.js';
import { buildImportGraph } from './graph/importGraph.js';
import { clusterByImportGraph } from './graph/cluster.js';
import { generateSnapshot } from './knowledge/snapshot.js';

function parseArgs(argv: string[]): CliArgs {
  const args: Record<string, string> = {};
  for (let i = 2; i < argv.length; i++) {
    const key = argv[i].replace(/^--/, '');
    if (i + 1 < argv.length && !argv[i + 1].startsWith('--')) {
      args[key] = argv[i + 1];
      i++;
    } else {
      args[key] = 'true';
    }
  }
  return {
    base: args.base,
    target: args.target,
    frontendPaths: (args['frontend-paths'] || '').split(',').filter(Boolean),
    diffDir: args['diff-dir'],
    output: args.output,
    mode: args.mode as CliArgs['mode'],
  };
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv);

  if (args.mode === 'snapshot') {
    const snapshot = await generateSnapshot(args.target, args.frontendPaths);
    fs.writeFileSync(args.output, JSON.stringify(snapshot, null, 2));
    console.error(`Snapshot generated: ${snapshot.applications.length} apps, ${snapshot.sharedPackages.length} shared packages`);
    process.exit(0);
  }

  if (!args.base || !args.target || !args.diffDir) {
    console.error('Error: --base, --target, --diff-dir required for analyze mode');
    process.exit(1);
  }

  const patchPath = `${args.diffDir}/raw.patch`;
  if (!fs.existsSync(patchPath)) {
    console.error(`Error: patch file not found: ${patchPath}`);
    process.exit(1);
  }
  const hunks = parseHunks(fs.readFileSync(patchPath, 'utf-8'), args.frontendPaths);

  // Create ts-morph Project for AST validation (lightweight mode, no TypeChecker)
  const project = new Project({
    useInMemoryFileSystem: false,
    skipFileDependencyResolution: true,
    compilerOptions: {
      allowJs: true,
      jsx: 'preserve' as any,
      target: 'ESNext' as any,
    },
  });

  // Load target worktree files mentioned in hunks for AST validation
  const changedFiles = new Set(hunks.map(h => h.file));
  for (const filePath of changedFiles) {
    const fullPath = path.join(args.target!, filePath);
    if (fs.existsSync(fullPath)) {
      try {
        project.addSourceFileAtPath(fullPath);
      } catch {
        // skip files that can't be parsed (e.g. binary, empty)
      }
    }
  }
  console.error(`[AST] Loaded ${project.getSourceFiles().length} source files for validation`);

  // Build import graph and cluster
  const graph = buildImportGraph(hunks, args.frontendPaths);
  const clusters = clusterByImportGraph(hunks, graph);

  // Build feature groups from clusters
  const featureGroups: FeatureGroup[] = [];

  for (let ci = 0; ci < clusters.length; ci++) {
    const cluster = clusters[ci];
    const files: FileAnalysisResult[] = [];
    const allSnippets: any[] = [];
    const allDocContexts: any[] = [];
    const allSignals: Set<string> = new Set();

    // Handle page-logic/ dedup at result layer
    const hasPagesFile = cluster.some(h => h.file.includes('/pages/'));
    const filteredHunks = cluster.filter(h => {
      if (h.file.includes('/page-logic/') && hasPagesFile) {
        // Has corresponding pages/ file, only use as supplemental
        return false; // skip signal extraction, keep as evidence
      }
      return true;
    });

    for (const hunk of filteredHunks) {
      const signals = extractSignals(hunk, args.frontendPaths, project);
      const signalTypes = signals.map(s => s.type);
      signalTypes.forEach(st => allSignals.add(st));

      const snippet = extractSnippet(hunk, signalTypes);
      allSnippets.push(snippet);

      const docCtx = collectDocContext(hunk);
      allDocContexts.push(docCtx);

      files.push({
        path: hunk.file,
        status: hunk.status,
        isRenameOnly: false,
        addedLines: hunk.addedLines.length,
        deletedLines: hunk.removedLines.length,
        signals,
        priority: 'P3' as const,
        classification: 'UNKNOWN' as const,
        isFunctional: false,
        snippet,
        docContext: docCtx,
      });
    }

    const classified = classifyGroup(Array.from(allSignals) as any, files);

    // Add page-logic/ files as evidence if they exist
    const pageLogicHunks = cluster.filter(h => h.file.includes('/page-logic/'));
    for (const plHunk of pageLogicHunks) {
      if (!files.some(f => f.path === plHunk.file)) {
        files.push({
          path: plHunk.file,
          status: plHunk.status,
          isRenameOnly: false,
          addedLines: plHunk.addedLines.length,
          deletedLines: plHunk.removedLines.length,
          signals: [],
          priority: 'P4' as const,
          classification: 'STYLE_ONLY' as const,
          isFunctional: false,
        });
      }
    }

    // Adjust confidence for page-logic-only groups
    let confidence = 0.5;
    if (cluster.every(h => h.file.includes('/page-logic/'))) {
      confidence -= 0.1; // auto-synced, lower confidence
    }
    if (allSignals.has('NEW_ROUTE') && allSignals.has('API_CALL')) confidence += 0.2;
    if (allSignals.has('NEW_PAGE')) confidence += 0.15;
    if (files.length >= 3) confidence += 0.1;
    if (files.length === 1 && allSignals.size === 1) confidence -= 0.2;
    if (allSignals.has('UNKNOWN')) confidence -= 0.1;
    confidence = Math.min(0.99, Math.max(0.1, parseFloat(confidence.toFixed(2))));

    featureGroups.push({
      id: `fg_${String(ci).padStart(3, '0')}`,
      type: classified.type,
      priority: classified.priority,
      isFunctional: classified.isFunctional,
      confidence,
      nameHint: Array.from(allSignals)[0] || 'UNKNOWN',
      files,
      allSignals: Array.from(allSignals) as any,
      snippets: allSnippets,
      docContexts: allDocContexts,
    });
  }

  const result: AnalysisResult = {
    mode: 'analyze',
    summary: {
      totalChangedFiles: hunks.length,
      analyzedFiles: featureGroups.reduce((acc, fg) => acc + fg.files.length, 0),
      featureGroups: featureGroups.length,
    },
    featureGroups,
  };

  fs.writeFileSync(args.output, JSON.stringify(result, null, 2));
  console.error(`Analysis complete: ${result.summary.featureGroups} groups`);
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});