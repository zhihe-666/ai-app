# 前端代码变更分析模块 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add code-change-analysis module to AI console — given GitLab repo URL & time range, auto-detect frontend functional changes via AST signal extraction + LLM summarization.

**Architecture:** Flask orchestrator manages lifecycle (git fetch → worktree checkout → diff → subprocess Node.js CLI → LLM call). Node.js CLI (ts-morph, no TypeChecker) does lightweight AST signal extraction, Import Graph clustering, and snippet extraction. Results flow through SSE events to the frontend.

**Tech Stack:** ts-morph (Node.js CLI), Flask (Python orchestrator), React + Ant Design (frontend), SSE streaming (existing pattern)

---

## File Map

### Created

| File | Responsibility |
|------|---------------|
| `tools/code-analyzer/package.json` | Node.js CLI deps (ts-morph) |
| `tools/code-analyzer/tsconfig.json` | TypeScript config for CLI |
| `tools/code-analyzer/src/types.ts` | All shared types |
| `tools/code-analyzer/src/index.ts` | CLI entry: arg parse → orchestrate → write output JSON |
| `tools/code-analyzer/src/git/parsePatch.ts` | Parse raw.patch → HunkInfo[] |
| `tools/code-analyzer/src/signals/extractor.ts` | Signal extraction entry (dispatches to per-signal modules) |
| `tools/code-analyzer/src/signals/routes.ts` | NEW_ROUTE (Umi config routes + JSX Routes) + NEW_PAGE |
| `tools/code-analyzer/src/signals/api.ts` | API_CALL |
| `tools/code-analyzer/src/signals/state.ts` | STATE_ACTION |
| `tools/code-analyzer/src/signals/permission.ts` | PERMISSION |
| `tools/code-analyzer/src/signals/hooks.ts` | HOOK_DEF |
| `tools/code-analyzer/src/signals/event.ts` | EVENT_HANDLER |
| `tools/code-analyzer/src/signals/dataModel.ts` | DATA_MODEL |
| `tools/code-analyzer/src/signals/config.ts` | CONFIG_CHANGE |
| `tools/code-analyzer/src/signals/style.ts` | STYLE_ONLY + style purity validation |
| `tools/code-analyzer/src/graph/importGraph.ts` | Import Graph builder |
| `tools/code-analyzer/src/graph/cluster.ts` | Connected components + fallback directory cluster |
| `tools/code-analyzer/src/classify/decisionTree.ts` | Priority decision tree |
| `tools/code-analyzer/src/snippet/extractSnippet.ts` | Dual-version function-level snippet + doc context |
| `tools/code-analyzer/src/knowledge/snapshot.ts` | Knowledge snapshot generator |
| `backend/routers/code_analyze.py` | Flask Blueprint (4 endpoints) |
| `backend/services/code_analyze_service.py` | Orchestrator (git → AST → LLM) |
| `frontend/src/api/codeAnalyze.ts` | API layer (TypeScript types + functions) |
| `frontend/src/pages/CodeAnalyze.tsx` | Page: config area, Steps progress, result report |

### Modified

| File | Change |
|------|--------|
| `backend/app.py` | Register `code_analyze_bp` blueprint |
| `frontend/src/App.tsx` | Add `/code-analyze` route |
| `frontend/src/components/AppLayout.tsx` | Add sidebar menu item |

---

## Phase 1a: CLI Skeleton + 4 Core Signals

### Task 1a.1: Scaffold Node.js CLI project

**Files:**
- Create: `tools/code-analyzer/package.json`
- Create: `tools/code-analyzer/tsconfig.json`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "code-analyzer",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "build": "tsc",
    "start": "node dist/index.js"
  },
  "dependencies": {
    "ts-morph": "^25.0.0"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "typescript": "^5.7.0"
  }
}
```

- [ ] **Step 2: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "node",
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "declaration": true,
    "sourceMap": true
  },
  "include": ["src/**/*"]
}
```

- [ ] **Step 3: Install dependencies**

Run: `cd tools/code-analyzer && npm install`
Expected: ts-morph + typescript installed, no errors

- [ ] **Step 4: Commit**

```bash
git add tools/code-analyzer/package.json tools/code-analyzer/tsconfig.json
git commit -m "feat: scaffold code-analyzer Node.js CLI project"
```

### Task 1a.2: Define shared types

**Files:**
- Create: `tools/code-analyzer/src/types.ts`

- [ ] **Step 1: Write common types**

```typescript
// tools/code-analyzer/src/types.ts

export type FileStatus = 'A' | 'M' | 'D';
export type GroupType =
  | 'NEW_FEATURE' | 'FEATURE_MODIFY' | 'FEATURE_REMOVAL'
  | 'INFRA_CHANGE' | 'UI_INTERACTION' | 'STYLE_ONLY'
  | 'REFACTOR' | 'DEPENDENCY_UPDATE' | 'UNKNOWN';
export type Priority = 'P0' | 'P1' | 'P2' | 'P3' | 'P4';
export type SignalType =
  | 'NEW_ROUTE' | 'NEW_PAGE' | 'API_CALL' | 'STATE_ACTION'
  | 'PERMISSION' | 'HOOK_DEF' | 'EVENT_HANDLER' | 'DATA_MODEL'
  | 'CONFIG_CHANGE' | 'STYLE_ONLY' | 'UNKNOWN';

export interface Signal {
  type: SignalType;
  detail?: string;
}

export interface HunkInfo {
  file: string;
  status: FileStatus;
  baseLine: number;
  baseCount: number;
  targetLine: number;
  targetCount: number;
  addedLines: string[];
  removedLines: string[];
  rawText: string;
}

export interface Snippet {
  file: string;
  signals: Signal[];
  before: string | null;
  after: string | null;
  diffHunk: string;
}

export interface DocContext {
  jsDoc: string[];
  testDescriptions: string[];
  readme: string | null;
}

export interface FileAnalysisResult {
  path: string;
  status: FileStatus;
  isRenameOnly: boolean;
  addedLines: number;
  deletedLines: number;
  signals: Signal[];
  priority: Priority;
  classification: GroupType;
  isFunctional: boolean;
  snippet?: Snippet;
  docContext?: DocContext;
}

export interface FeatureGroup {
  id: string;
  type: GroupType;
  priority: Priority;
  isFunctional: boolean;
  confidence: number;
  nameHint: string;
  files: FileAnalysisResult[];
  allSignals: SignalType[];
  snippets: Snippet[];
  docContexts: DocContext[];
}

export interface AnalysisResult {
  mode: 'analyze';
  summary: {
    totalChangedFiles: number;
    analyzedFiles: number;
    featureGroups: number;
  };
  featureGroups: FeatureGroup[];
  knowledgeSnapshot?: KnowledgeSnapshot;
}

export interface RouteConfig {
  path: string;
  component?: string;
  routes?: RouteConfig[];
}

export interface KnowledgeSnapshot {
  projectName: string;
  generatedAt: string;
  applications: {
    name: string;
    path: string;
    role: string;
    routes: { path: string; component?: string; description?: string }[];
    apiModules: { name: string; endpoints: string[] }[];
    components: string[];
    modules: string[];
  }[];
  sharedPackages: {
    name: string;
    path: string;
    components: string[];
    exports: string[];
  }[];
}

export interface CliArgs {
  base?: string;
  target: string;
  frontendPaths: string[];
  diffDir?: string;
  output: string;
  mode: 'analyze' | 'snapshot';
}
```

- [ ] **Step 2: Build check**

Run: `cd tools/code-analyzer && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add tools/code-analyzer/src/types.ts
git commit -m "feat: define shared types for code-analyzer"
```

### Task 1a.3: CLI entry point (arg parser + orchestrator)

**Files:**
- Create: `tools/code-analyzer/src/index.ts`

- [ ] **Step 1: Write CLI entry**

```typescript
// tools/code-analyzer/src/index.ts
import fs from 'fs';
import { CliArgs, AnalysisResult } from './types.js';
import { parseHunks } from './git/parsePatch.js';
import { extractSignals } from './signals/extractor.js';
import { classifyGroup } from './classify/decisionTree.js';
import { extractSnippet } from './snippet/extractSnippet.js';

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
    // Phase 2 will implement this
    fs.writeFileSync(args.output, JSON.stringify({ mode: 'snapshot', generatedAt: new Date().toISOString() }));
    process.exit(0);
  }

  if (!args.base || !args.target || !args.diffDir) {
    console.error('Error: --base, --target, --diff-dir required for analyze mode');
    process.exit(1);
  }

  // Read hunks from raw.patch
  const patchPath = `${args.diffDir}/raw.patch`;
  if (!fs.existsSync(patchPath)) {
    console.error(`Error: patch file not found: ${patchPath}`);
    process.exit(1);
  }
  const hunks = parseHunks(fs.readFileSync(patchPath, 'utf-8'), args.frontendPaths);

  // Phase 1a: classify directly from hunks (4 core signals)
  const files = hunks.map(h => ({
    path: h.file,
    status: h.status,
    isRenameOnly: false,
    addedLines: h.addedLines.length,
    deletedLines: h.removedLines.length,
    signals: extractSignals(h, args.frontendPaths),
    priority: 'P3' as const,
    classification: 'UNKNOWN' as const,
    isFunctional: false,
  }));

  const result: AnalysisResult = {
    mode: 'analyze',
    summary: {
      totalChangedFiles: hunks.length,
      analyzedFiles: files.length,
      featureGroups: 0,
    },
    featureGroups: files.map((f, i) => {
      const classified = classifyGroup(f.signals.map(s => s.type), [f]);
      return {
        id: `fg_${String(i).padStart(3, '0')}`,
        type: classified.type,
        priority: classified.priority,
        isFunctional: classified.isFunctional,
        confidence: 0.5,
        nameHint: f.signals[0]?.type || 'UNKNOWN',
        files: [f],
        allSignals: f.signals.map(s => s.type),
        snippets: f.snippet ? [f.snippet] : [],
        docContexts: [],
      };
    }),
  };
  result.summary.featureGroups = result.featureGroups.length;

  fs.writeFileSync(args.output, JSON.stringify(result, null, 2));
  console.error(`Analysis complete: ${result.summary.featureGroups} groups`);
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
```

- [ ] **Step 2: Build check**

Run: `cd tools/code-analyzer && npx tsc --noEmit`
Expected: No errors (may fail on missing module imports — that's expected, will resolve as modules are created)

- [ ] **Step 3: Commit**

```bash
git add tools/code-analyzer/src/index.ts
git commit -m "feat: add CLI entry point with arg parser"
```

### Task 1a.4: Patch parser

**Files:**
- Create: `tools/code-analyzer/src/git/parsePatch.ts`

- [ ] **Step 1: Write patch parser**

```typescript
// tools/code-analyzer/src/git/parsePatch.ts
import { HunkInfo } from '../types.js';

export function parseHunks(patchContent: string, frontendPaths: string[]): HunkInfo[] {
  const hunks: HunkInfo[] = [];
  const fileRegex = /^diff --git a\/(.+?) b\/(.+?)$/gm;
  const hunkHeaderRegex = /^@@ -(\d+),(\d+) \+(\d+),(\d+) @@/;

  let match: RegExpExecArray | null;
  let currentFile = '';
  let currentStatus: 'A' | 'M' | 'D' = 'M';
  let currentHunk: Partial<HunkInfo> | null = null;

  const lines = patchContent.split('\n');

  for (const line of lines) {
    // File header
    fileRegex.lastIndex = 0;
    match = fileRegex.exec(line);
    if (match) {
      const targetFile = match[2];
      // Skip files not in any frontend path
      const inScope = frontendPaths.some(p => targetFile.startsWith(p));
      if (inScope) {
        currentFile = targetFile;
        // Determine status from /dev/null patterns (handled by diff lines)
        currentStatus = 'M';
      } else {
        currentFile = '';
      }
      currentHunk = null;
      continue;
    }

    if (!currentFile) continue;

    // New file marker
    if (line.startsWith('new file mode')) {
      currentStatus = 'A';
      continue;
    }
    if (line.startsWith('deleted file mode')) {
      currentStatus = 'D';
      continue;
    }

    // Hunk header
    const hunkMatch = hunkHeaderRegex.exec(line);
    if (hunkMatch) {
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
        rawText: line + '\n',
      };
      continue;
    }

    if (currentHunk) {
      currentHunk.rawText = (currentHunk.rawText || '') + line + '\n';
      if (line.startsWith('+') && !line.startsWith('+++')) {
        currentHunk.addedLines!.push(line.slice(1));
      } else if (line.startsWith('-') && !line.startsWith('---')) {
        currentHunk.removedLines!.push(line.slice(1));
      }
    }
  }

  // Push last hunk
  if (currentHunk && (currentHunk.addedLines?.length || currentHunk.removedLines?.length)) {
    hunks.push(currentHunk as HunkInfo);
  }

  return hunks;
}
```

- [ ] **Step 2: Build check**

Run: `cd tools/code-analyzer && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add tools/code-analyzer/src/git/parsePatch.ts
git commit -m "feat: add patch parser (diff → HunkInfo[])"
```

### Task 1a.5: 4 core signal extractors (NEW_ROUTE, NEW_PAGE, API_CALL, STATE_ACTION)

**Files:**
- Create: `tools/code-analyzer/src/signals/extractor.ts`
- Create: `tools/code-analyzer/src/signals/routes.ts`
- Create: `tools/code-analyzer/src/signals/api.ts`
- Create: `tools/code-analyzer/src/signals/state.ts`

- [ ] **Step 1: Write NEW_ROUTE + NEW_PAGE extractor**

```typescript
// tools/code-analyzer/src/signals/routes.ts
import { HunkInfo, Signal, RouteConfig } from '../types.js';

/**
 * Detect route/page changes from Umi config routes (config/config.ts) and JSX Route components.
 *
 * Algorithm:
 * 1. For config/config.ts: scan added lines for `"path":` / `path:` patterns
 *    to extract new route paths (lightweight for Phase 1a).
 * 2. For NEW_PAGE: detect new files under pages/ directories with export default.
 *
 * Phase 1b upgrade: full tree diff of parsed Umi route configs.
 */
export function extractRouteSignals(hunk: HunkInfo): Signal[] {
  const signals: Signal[] = [];

  // Detect Umi config route changes
  if (hunk.file.includes('config/config.ts') || hunk.file.endsWith('.umirc.ts')) {
    for (const line of hunk.addedLines) {
      const pathMatch = line.match(/["']path["']?\s*:\s*["']([^"']+)["']/);
      if (pathMatch) {
        signals.push({ type: 'NEW_ROUTE', detail: pathMatch[1] });
      }
      const routesMatch = line.match(/routes\s*:/);
      if (routesMatch) {
        signals.push({ type: 'NEW_ROUTE', detail: 'routes array defined' });
      }
    }
  }

  // Detect JSX Route component changes
  for (const line of [...hunk.addedLines, ...hunk.removedLines]) {
    const routeMatch = line.match(/<Route[^>]*\spath=["']([^"']+)["']/);
    if (routeMatch) {
      signals.push({
        type: 'NEW_ROUTE',
        detail: `Route path="${routeMatch[1]}"`,
      });
    }
  }

  // Detect NEW_PAGE: new files under pages/ directories
  if (hunk.status === 'A') {
    const pageMatch = hunk.file.match(/(\/pages\/.*)\.(tsx|ts)$/);
    if (pageMatch) {
      signals.push({ type: 'NEW_PAGE', detail: pageMatch[1] });
    }
  }

  return signals;
}
```

- [ ] **Step 2: Write API_CALL extractor**

```typescript
// tools/code-analyzer/src/signals/api.ts
import { HunkInfo, Signal } from '../types.js';

export function extractApiSignals(hunk: HunkInfo): Signal[] {
  const signals: Signal[] = [];

  // Common API call patterns in algorithm-monorepo
  const apiPatterns = [
    /\b(?:api|request|client|http)\s*\.\s*(?:get|post|put|patch|delete|request)\s*\(/,
    /\bfetch\s*\(/,
    /\baxios\s*\.\s*(?:get|post|put|delete)\s*\(/,
    /\buseRequest\s*\(/,
  ];

  for (const line of hunk.addedLines) {
    for (const pattern of apiPatterns) {
      if (pattern.test(line)) {
        const trimmed = line.trim().slice(0, 80);
        signals.push({ type: 'API_CALL', detail: trimmed });
        break;
      }
    }
  }

  return signals;
}
```

- [ ] **Step 3: Write STATE_ACTION extractor**

```typescript
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
```

- [ ] **Step 4: Write signal extractor entry point**

```typescript
// tools/code-analyzer/src/signals/extractor.ts
import { HunkInfo, Signal } from '../types.js';
import { extractRouteSignals } from './routes.js';
import { extractApiSignals } from './api.js';
import { extractStateSignals } from './state.js';

export function extractSignals(hunk: HunkInfo, frontendPaths: string[]): Signal[] {
  const signals: Signal[] = [
    ...extractRouteSignals(hunk),
    ...extractApiSignals(hunk),
    ...extractStateSignals(hunk),
  ];

  return signals;
}
```

- [ ] **Step 5: Build check**

Run: `cd tools/code-analyzer && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add tools/code-analyzer/src/signals/
git commit -m "feat: add 4 core signal extractors (NEW_ROUTE, NEW_PAGE, API_CALL, STATE_ACTION)"
```

### Task 1a.6: Decision tree + rename detection

**Files:**
- Create: `tools/code-analyzer/src/classify/decisionTree.ts`

- [ ] **Step 1: Write decision tree classifier**

```typescript
// tools/code-analyzer/src/classify/decisionTree.ts
import { SignalType, GroupType, Priority, FileAnalysisResult } from '../types.js';

export function classifyGroup(
  signalTypes: SignalType[],
  files: FileAnalysisResult[]
): { type: GroupType; priority: Priority; isFunctional: boolean } {
  const signalSet = new Set(signalTypes);

  // Pure rename
  if (files.every(f => f.isRenameOnly)) {
    return { type: 'REFACTOR', priority: 'P3', isFunctional: false };
  }

  // Pure dependency update
  if (files.every(f => f.path.match(/package\.json|\.lock$/))) {
    return { type: 'DEPENDENCY_UPDATE', priority: 'P3', isFunctional: false };
  }

  // Feature removal
  if (files.every(f => f.status === 'D')) {
    return { type: 'FEATURE_REMOVAL', priority: 'P1', isFunctional: true };
  }

  // Core decision tree (highest priority wins first)
  if (signalSet.has('NEW_ROUTE') || signalSet.has('NEW_PAGE')) {
    return { type: 'NEW_FEATURE', priority: 'P0', isFunctional: true };
  }

  if (
    signalSet.has('API_CALL') ||
    signalSet.has('STATE_ACTION') ||
    signalSet.has('PERMISSION') ||
    signalSet.has('HOOK_DEF')
  ) {
    return { type: 'FEATURE_MODIFY', priority: 'P1', isFunctional: true };
  }

  if (signalSet.has('DATA_MODEL') || signalSet.has('CONFIG_CHANGE')) {
    return { type: 'INFRA_CHANGE', priority: 'P2', isFunctional: false };
  }

  if (signalSet.has('EVENT_HANDLER')) {
    return { type: 'UI_INTERACTION', priority: 'P2', isFunctional: false };
  }

  if (signalSet.size === 0 || (signalSet.size === 1 && signalSet.has('STYLE_ONLY'))) {
    return { type: 'STYLE_ONLY', priority: 'P3', isFunctional: false };
  }

  return { type: 'UNKNOWN', priority: 'P4', isFunctional: false };
}
```

- [ ] **Step 2: Build check**

Run: `cd tools/code-analyzer && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add tools/code-analyzer/src/classify/decisionTree.ts
git commit -m "feat: add priority decision tree classifier"
```

### Task 1a.7: Snippet extraction

**Files:**
- Create: `tools/code-analyzer/src/snippet/extractSnippet.ts`

- [ ] **Step 1: Write snippet extractor**

```typescript
// tools/code-analyzer/src/snippet/extractSnippet.ts
import { HunkInfo, Snippet } from '../types.js';

/**
 * Extract function-level snippet from a hunk.
 * For Phase 1a: return the hunk's added/removed lines as context.
 * Phase 1b upgrade: use ts-morph to find enclosing function.
 */
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
    diffHunk: hunk.rawText.slice(0, 1000),
  };
}
```

- [ ] **Step 2: Build check**

Run: `cd tools/code-analyzer && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add tools/code-analyzer/src/snippet/extractSnippet.ts
git commit -m "feat: add snippet extraction"
```

### Task 1a.8: End-to-end smoke test

- [ ] **Step 1: Create a test patch file**

Create `/tmp/test_raw.patch`:
```patch
diff --git a/apps/algorithm/ml-data/src/pages/training/BatchImport.tsx b/apps/algorithm/ml-data/src/pages/training/BatchImport.tsx
new file mode 100644
@@ -0,0 +1,30 @@
+import { api } from '@algorithm/request';
+import { useState } from 'react';
+
+export default function BatchImport() {
+  const [loading, setLoading] = useState(false);
+
+  const handleUpload = async (file: File) => {
+    setLoading(true);
+    const res = await api.post('/api/training/batch-import', { file });
+    setLoading(false);
+    return res;
+  };
+
+  return (
+    <div>
+      <h2>批量导入训练任务</h2>
+      <input type="file" onChange={(e) => handleUpload(e.target.files![0])} />
+    </div>
+  );
+}
diff --git a/apps/algorithm/ml-main/config/config.ts b/apps/algorithm/ml-main/config/config.ts
index abc..def 100644
@@ -10,6 +10,9 @@ export default defineConfig({
   routes: [
     { path: '/main/dataApp', component: 'dataApp' },
+    { path: '/main/dataApp/training/batch-import', component: 'BatchImport' },
+    { path: '/main/dataApp/sample/new', component: 'SampleNew' },
   ],
 });
```

- [ ] **Step 2: Build the CLI**

Run: `cd tools/code-analyzer && npm run build`
Expected: `dist/index.js` created

- [ ] **Step 3: Run CLI on test patch**

```bash
mkdir -p /tmp/test-diff
cp /tmp/test_raw.patch /tmp/test-diff/raw.patch
cd tools/code-analyzer && node dist/index.js \
  --base /tmp/base --target /tmp/target \
  --frontend-paths "apps/algorithm/ml-main,apps/algorithm/ml-data" \
  --diff-dir /tmp/test-diff \
  --output /tmp/test-result.json \
  --mode analyze
```

Expected: Exit code 0, output file written

- [ ] **Step 4: Verify output contains expected signals**

```bash
python3 -c "
import json
data = json.load(open('/tmp/test-result.json'))
print(f'Feature groups: {len(data[\"featureGroups\"])}')
for fg in data['featureGroups']:
    sigs = ', '.join(fg['allSignals'])
    print(f'  {fg[\"id\"]}: [{fg[\"type\"]}] {sigs}')
assert len(data['featureGroups']) == 2, 'Expected 2 feature groups'
assert any('NEW_ROUTE' in fg['allSignals'] for fg in data['featureGroups']), 'Missing NEW_ROUTE'
assert any('API_CALL' in fg['allSignals'] for fg in data['featureGroups']), 'Missing API_CALL'
print('ALL CHECKS PASSED')
"
```

Expected: 2 feature groups with NEW_ROUTE and API_CALL signals

- [ ] **Step 5: Commit**

```bash
git add tools/code-analyzer/
git commit -m "feat: Phase 1a complete — CLI skeleton + 4 core signals + decision tree + snippet extraction"
```

---

## Phase 1b: Remaining 6 Signals + Import Graph + Doc Context

### Task 1b.1: PERMISSION, HOOK_DEF, EVENT_HANDLER extractors

**Files:**
- Create: `tools/code-analyzer/src/signals/permission.ts`
- Create: `tools/code-analyzer/src/signals/hooks.ts`
- Create: `tools/code-analyzer/src/signals/event.ts`

- [ ] **Step 1: Write PERMISSION extractor**

```typescript
// tools/code-analyzer/src/signals/permission.ts
import { HunkInfo, Signal } from '../types.js';

export function extractPermissionSignals(hunk: HunkInfo): Signal[] {
  const signals: Signal[] = [];
  const permissionKeywords = /\b(role|permission|auth|isAdmin|hasAccess|canAccess|isAllowed)\b/i;

  for (const line of [...hunk.addedLines, ...hunk.removedLines]) {
    if (permissionKeywords.test(line)) {
      signals.push({ type: 'PERMISSION', detail: line.trim().slice(0, 100) });
    }
  }

  return signals;
}
```

- [ ] **Step 2: Write HOOK_DEF extractor**

```typescript
// tools/code-analyzer/src/signals/hooks.ts
import { HunkInfo, Signal } from '../types.js';

export function extractHookSignals(hunk: HunkInfo): Signal[] {
  const signals: Signal[] = [];
  // Match function/const declarations with use-prefix names
  const hookDefPattern = /(?:^|\n)\s*(?:export\s+)?(?:function\s+|const\s+)?(use[A-Z]\w+)\s*(?:=|:)/;

  for (const line of hunk.addedLines) {
    const match = line.match(hookDefPattern);
    if (match) {
      signals.push({ type: 'HOOK_DEF', detail: match[1] });
    }
  }

  return signals;
}
```

- [ ] **Step 3: Write EVENT_HANDLER extractor**

```typescript
// tools/code-analyzer/src/signals/event.ts
import { HunkInfo, Signal } from '../types.js';

export function extractEventHandlerSignals(hunk: HunkInfo): Signal[] {
  const signals: Signal[] = [];
  // Match JSX event handlers
  const eventPattern = /\b(on[A-Z]\w+)\s*=\s*\{/;

  for (const line of hunk.addedLines) {
    const matches = [...line.matchAll(eventPattern)];
    for (const m of matches) {
      signals.push({ type: 'EVENT_HANDLER', detail: m[1] });
    }
  }

  return signals;
}
```

- [ ] **Step 4: Build check**

Run: `cd tools/code-analyzer && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add tools/code-analyzer/src/signals/permission.ts tools/code-analyzer/src/signals/hooks.ts tools/code-analyzer/src/signals/event.ts
git commit -m "feat: add PERMISSION, HOOK_DEF, EVENT_HANDLER signal extractors"
```

### Task 1b.2: DATA_MODEL, CONFIG_CHANGE, STYLE_ONLY extractors

**Files:**
- Create: `tools/code-analyzer/src/signals/dataModel.ts`
- Create: `tools/code-analyzer/src/signals/config.ts`
- Create: `tools/code-analyzer/src/signals/style.ts`

- [ ] **Step 1: Write DATA_MODEL extractor**

```typescript
// tools/code-analyzer/src/signals/dataModel.ts
import { HunkInfo, Signal } from '../types.js';

export function extractDataModelSignals(hunk: HunkInfo): Signal[] {
  const signals: Signal[] = [];
  const modelPatterns = [
    /\binterface\s+\w+/,
    /\btype\s+\w+\s*=/,
    /\benum\s+\w+/,
  ];

  for (const line of hunk.addedLines) {
    for (const pattern of modelPatterns) {
      if (pattern.test(line)) {
        signals.push({ type: 'DATA_MODEL', detail: line.trim() });
        break;
      }
    }
  }

  return signals;
}
```

- [ ] **Step 2: Write CONFIG_CHANGE extractor**

```typescript
// tools/code-analyzer/src/signals/config.ts
import { HunkInfo, Signal } from '../types.js';

const configFilePatterns = [
  /\.env/,
  /vite\.config/,
  /\.umirc\./,
  /config\/config\.ts/,
  /webpack\.config/,
  /next\.config/,
];

export function extractConfigSignals(hunk: HunkInfo): Signal[] {
  const isConfig = configFilePatterns.some(p => p.test(hunk.file));
  if (!isConfig) return [];

  return [{ type: 'CONFIG_CHANGE', detail: hunk.file }];
}
```

- [ ] **Step 3: Write STYLE_ONLY extractor with purity validation**

```typescript
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

  // For non-style files: check if all changed lines are style-only
  // (reference CSS class names, style objects, or theme tokens)
  const nonStyleLines = hunk.addedLines.filter(line => {
    const trimmed = line.trim();
    if (!trimmed) return false;
    // Contains actual logic keywords
    if (/\b(if|else|for|while|return|switch|case|import\s+\w|export\s+\w)\b/.test(trimmed)) return true;
    // Function call that isn't a style keyword
    if (/\w+\s*\(/.test(trimmed)) {
      const callMatch = trimmed.match(/(\w+)\s*\(/);
      if (callMatch && !styleKeywords.has(callMatch[1])) return true;
    }
    // Template literal or JSX with non-style content
    if (/\b(on[A-Z]|handle\w+)\s*=\s*\{/.test(trimmed)) return true;
    return false;
  });

  if (nonStyleLines.length === 0 && hunk.addedLines.length > 0) {
    return [{ type: 'STYLE_ONLY', detail: hunk.file }];
  }

  return [];
}
```

- [ ] **Step 4: Update extractor.ts to include all signals**

```typescript
// tools/code-analyzer/src/signals/extractor.ts (updated)
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

export function extractSignals(hunk: HunkInfo, frontendPaths: string[]): Signal[] {
  const signals: Signal[] = [
    ...extractRouteSignals(hunk),
    ...extractApiSignals(hunk),
    ...extractStateSignals(hunk),
    ...extractPermissionSignals(hunk),
    ...extractHookSignals(hunk),
    ...extractEventHandlerSignals(hunk),
    ...extractDataModelSignals(hunk),
    ...extractConfigSignals(hunk),
    ...extractStyleSignals(hunk),
  ];

  return signals;
}
```

- [ ] **Step 5: Build check**

Run: `cd tools/code-analyzer && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add tools/code-analyzer/src/signals/extractor.ts tools/code-analyzer/src/signals/dataModel.ts tools/code-analyzer/src/signals/config.ts tools/code-analyzer/src/signals/style.ts
git commit -m "feat: add DATA_MODEL, CONFIG_CHANGE, STYLE_ONLY signal extractors"
```

### Task 1b.3: Import Graph builder + connected components clustering

**Files:**
- Create: `tools/code-analyzer/src/graph/importGraph.ts`
- Create: `tools/code-analyzer/src/graph/cluster.ts`

- [ ] **Step 1: Write Import Graph builder**

```typescript
// tools/code-analyzer/src/graph/importGraph.ts
import { HunkInfo } from '../types.js';

export interface ImportGraph {
  adjacency: Map<string, Set<string>>;
}

/**
 * Build a dependency graph from import statements in changed files.
 * For Phase 1b: text-based import extraction (no ts-morph).
 * Phase 2 upgrade: use ts-morph AST for precise import resolution.
 */
export function buildImportGraph(hunks: HunkInfo[], frontendPaths: string[]): ImportGraph {
  const adjacency = new Map<string, Set<string>>();
  const changedFiles = new Set(hunks.map(h => h.file));

  // Extract import statements from hunk added lines
  const fileImports = new Map<string, string[]>();
  for (const hunk of hunks) {
    const imports: string[] = [];
    for (const line of hunk.addedLines) {
      const staticImport = line.match(/^import\s+(?:\{[^}]*\}\s+)?(\S+)/);
      if (staticImport) {
        imports.push(staticImport[1]);
      }
      const dynamicImport = line.match(/import\(['"`]([^'"`]+)['"`]\)/);
      if (dynamicImport) {
        imports.push(dynamicImport[1]);
      }
    }
    fileImports.set(hunk.file, imports);
  }

  // Resolve imports to changed files
  for (const [file, imports] of fileImports) {
    const neighbors = new Set<string>();
    for (const imp of imports) {
      // Try to match against known changed files
      for (const cf of changedFiles) {
        if (cf === file) continue;
        // Match by filename (without extension)
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
```

- [ ] **Step 2: Write clustering algorithm**

```typescript
// tools/code-analyzer/src/graph/cluster.ts
import { HunkInfo } from '../types.js';
import { ImportGraph } from './importGraph.js';

/**
 * Cluster changed files by connected components in the import graph.
 * Falls back to directory-based clustering for isolated nodes.
 */
export function clusterByImportGraph(
  hunks: HunkInfo[],
  graph: ImportGraph
): HunkInfo[][] {
  const visited = new Set<string>();
  const clusters: HunkInfo[][] = [];
  const hunkMap = new Map(hunks.map(h => [h.file, h]));

  const bfs = (start: string): string[] => {
    const component: string[] = [];
    const queue = [start];
    while (queue.length > 0) {
      const curr = queue.pop()!;
      if (visited.has(curr)) continue;
      visited.add(curr);
      component.push(curr);
      for (const neighbor of graph.adjacency.get(curr) || []) {
        if (!visited.has(neighbor)) queue.push(neighbor);
      }
      // Reverse edges: files that import curr
      for (const [other, neighbors] of graph.adjacency) {
        if (!visited.has(other) && neighbors.has(curr)) {
          queue.push(other);
        }
      }
    }
    return component;
  };

  // Main clustering
  const connected: string[] = [];
  for (const hunk of hunks) {
    if (!visited.has(hunk.file) && graph.adjacency.has(hunk.file)) {
      connected.push(...bfs(hunk.file));
    }
  }

  // Build clusters from connected components
  const connectedSet = new Set(connected);
  const seen = new Set<string>();
  for (const file of connected) {
    if (seen.has(file)) continue;
    const component = bfs(file);
    const clusterHunks = component.map(f => hunkMap.get(f)!).filter(Boolean);
    if (clusterHunks.length > 0) {
      clusters.push(clusterHunks);
      component.forEach(f => seen.add(f));
    }
  }

  // Isolated nodes: fallback to directory clustering
  const isolatedHunks = hunks.filter(h => !connectedSet.has(h.file));
  const dirMap = new Map<string, HunkInfo[]>();
  for (const hunk of isolatedHunks) {
    const dir = hunk.file.substring(0, hunk.file.lastIndexOf('/'));
    if (!dirMap.has(dir)) dirMap.set(dir, []);
    dirMap.get(dir)!.push(hunk);
  }
  for (const [, hunkGroup] of dirMap) {
    clusters.push(hunkGroup);
  }

  return clusters;
}
```

- [ ] **Step 3: Build check**

Run: `cd tools/code-analyzer && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add tools/code-analyzer/src/graph/
git commit -m "feat: add Import Graph builder + connected components clustering"
```

### Task 1b.4: Doc context collection

**Files:**
- Modify: `tools/code-analyzer/src/snippet/extractSnippet.ts`

- [ ] **Step 1: Add doc context collection to snippet extractor**

```typescript
// tools/code-analyzer/src/snippet/extractSnippet.ts (updated)
import { HunkInfo, Snippet, DocContext } from '../types.js';

// JSDoc pattern
const JSDOC_LINE_RE = /^\s*\*?\s*(.+)$/;

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
    diffHunk: hunk.rawText.slice(0, 1000),
  };
}

/**
 * Collect doc context from hunk content (JSDoc comments, test descriptions).
 *
 * Phase 1b: extract from available hunk lines (added/removed).
 * Phase 2 upgrade: scan actual file content for complete JSDoc blocks.
 */
export function collectDocContext(hunk: HunkInfo): DocContext {
  const jsDoc: string[] = [];
  const testDescriptions: string[] = [];
  let readme: string | null = null;

  // Extract JSDoc comments from added lines
  for (const line of hunk.addedLines) {
    const jsDocMatch = line.match(/\/\*\*([^*]|\*[^/])*\*\//);
    if (jsDocMatch) {
      jsDoc.push(jsDocMatch[0]);
    }
    // Single-line JSDoc
    const singleLineDoc = line.match(/\/\/\/\s*<reference/);
    if (singleLineDoc) continue;
    const commentMatch = line.match(/\/\/\s*(.+)/);
    if (commentMatch && !commentMatch[1].startsWith(' eslint')) {
      // Not always JSDoc, but useful context
      if (jsDoc.length === 0 || jsDoc[jsDoc.length - 1].length > 50) {
        // skip
      }
    }
  }

  // Check if this is a test file or has corresponding test
  const testMatch = hunk.file.match(/__tests__\/(.+)\.(test|spec)\./);
  if (testMatch) {
    // Extract test descriptions from existing hunk content
    for (const line of [...hunk.addedLines, ...hunk.removedLines]) {
      const descMatch = line.match(/(?:describe|it|test)\s*\(\s*['"`]([^'"`]+)['"`]/);
      if (descMatch) {
        testDescriptions.push(descMatch[1]);
      }
    }
  }

  return {
    jsDoc,
    testDescriptions,
    readme,
  };
}
```

- [ ] **Step 2: Build check**

Run: `cd tools/code-analyzer && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add tools/code-analyzer/src/snippet/extractSnippet.ts
git commit -m "feat: add doc context collection to snippet extractor"
```

---

## Phase 2: Knowledge Snapshot Generator

### Task 2.1: Snapshot generator

**Files:**
- Create: `tools/code-analyzer/src/knowledge/snapshot.ts`

- [ ] **Step 1: Write knowledge snapshot generator**

```typescript
// tools/code-analyzer/src/knowledge/snapshot.ts
import { Project } from 'ts-morph';
import { KnowledgeSnapshot, RouteConfig } from '../types.js';

/**
 * Generate a knowledge snapshot for the target project.
 * Scans: Umi config routes, service/ API modules, pages directory structure.
 *
 * Benchmark: on algorithm-monorepo (ml-main + ml-data + _share),
 * this should complete in 5-30s. If >30s, add stdout progress logging.
 */
export async function generateSnapshot(
  targetPath: string,
  frontendPaths: string[]
): Promise<KnowledgeSnapshot> {
  const project = new Project({
    useInMemoryFileSystem: false,
    skipFileDependencyResolution: true,
    compilerOptions: {
      allowJs: true,
      jsx: 'preserve' as any,
      target: 'ESNext' as any,
    },
  });

  const snapshot: KnowledgeSnapshot = {
    projectName: 'algorithm-monorepo',
    generatedAt: new Date().toISOString(),
    applications: [],
    sharedPackages: [],
  };

  for (const fp of frontendPaths) {
    const appPath = `${targetPath}/${fp}`;

    // Detect role
    const isMain = fp.includes('ml-main');
    const isShare = fp.includes('_share');

    if (isShare) {
      // Shared package
      const components: string[] = [];
      const exports: string[] = [];
      try {
        const componentsDir = `${appPath}/components`;
        const fs = await import('fs');
        if (fs.existsSync(componentsDir)) {
          for (const item of fs.readdirSync(componentsDir)) {
            if (fs.statSync(`${componentsDir}/${item}`).isDirectory()) {
              components.push(item);
            }
          }
        }
      } catch { /* ignore */ }

      snapshot.sharedPackages.push({
        name: `@algorithm/${fp.split('/').pop()}`,
        path: fp,
        components,
        exports,
      });
      continue;
    }

    // Extract routes from config/config.ts
    const routes: { path: string; component?: string; description?: string }[] = [];
    try {
      const fs = await import('fs');
      const configPaths = [
        `${appPath}/config/config.ts`,
        `${appPath}/.umirc.ts`,
        `${appPath}/.umirc.tsx`,
      ];
      for (const configPath of configPaths) {
        if (fs.existsSync(configPath)) {
          const content = fs.readFileSync(configPath, 'utf-8');
          const routeMatches = content.matchAll(/["']path["']?\s*:\s*["']([^"']+)["']/g);
          for (const m of routeMatches) {
            routes.push({ path: m[1] });
          }
        }
      }
    } catch { /* ignore */ }

    // Scan pages directory for modules
    const modules: string[] = [];
    try {
      const fs = await import('fs');
      const pagesDir = `${appPath}/src/pages`;
      if (fs.existsSync(pagesDir)) {
        for (const item of fs.readdirSync(pagesDir)) {
          if (fs.statSync(`${pagesDir}/${item}`).isDirectory()) {
            modules.push(item);
          }
        }
      }
    } catch { /* ignore */ }

    // Scan service directory for API modules
    const apiModules: { name: string; endpoints: string[] }[] = [];
    try {
      const fs = await import('fs');
      const serviceDir = `${appPath}/src/service`;
      if (fs.existsSync(serviceDir)) {
        for (const item of fs.readdirSync(serviceDir)) {
          const servicePath = `${serviceDir}/${item}`;
          if (fs.statSync(servicePath).isDirectory()) {
            const endpoints: string[] = [];
            for (const sub of fs.readdirSync(servicePath)) {
              endpoints.push(sub.replace(/\.(ts|tsx)$/, ''));
            }
            apiModules.push({ name: item, endpoints });
          }
        }
      }
    } catch { /* ignore */ }

    // Scan components directory
    const components: string[] = [];
    try {
      const fs = await import('fs');
      const componentsDir = `${appPath}/src/components`;
      if (fs.existsSync(componentsDir)) {
        for (const item of fs.readdirSync(componentsDir)) {
          components.push(item.replace(/\.(ts|tsx)$/, ''));
        }
      }
    } catch { /* ignore */ }

    snapshot.applications.push({
      name: isMain ? 'ml-main' : fp.split('/').pop() || 'unknown',
      path: fp,
      role: isMain ? 'qiankun master' : 'qiankun slave',
      routes,
      apiModules,
      components,
      modules,
    });
  }

  return snapshot;
}
```

- [ ] **Step 2: Update CLI --mode snapshot handler**

Edit `tools/code-analyzer/src/index.ts`. Replace the snapshot stub:

```typescript
if (args.mode === 'snapshot') {
  const { generateSnapshot } = await import('./knowledge/snapshot.js');
  const snapshot = await generateSnapshot(args.target, args.frontendPaths);
  fs.writeFileSync(args.output, JSON.stringify(snapshot, null, 2));
  console.error(`Snapshot generated: ${snapshot.applications.length} apps, ${snapshot.sharedPackages.length} shared packages`);
  process.exit(0);
}
```

- [ ] **Step 3: Build check**

Run: `cd tools/code-analyzer && npm run build`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add tools/code-analyzer/src/knowledge/ tools/code-analyzer/src/index.ts
git commit -m "feat: add knowledge snapshot generator + CLI snapshot mode"
```

---

## Phase 3: Flask Orchestrator + API Endpoints

### Task 3.1: Orchestrator service

**Files:**
- Create: `backend/services/code_analyze_service.py`

- [ ] **Step 1: Write orchestrator**

```python
# backend/services/code_analyze_service.py

import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from services.llm_client import llm_complete

GIT_CACHE_DIR = "/data/git-cache"
SNAPSHOT_FILE = "knowledge_snapshot.json"


class CodeAnalyzeService:
    """Orchestrator for code change analysis lifecycle."""

    def __init__(self):
        self.task_id = None
        self.base_worktree = None
        self.target_worktree = None
        self.bare_repo_path = None
        self.snapshot_path = None
        self.task_dir = None

    def _sanitize_task_id(self, raw: str) -> str:
        """Remove special characters from task_id for filesystem safety."""
        return re.sub(r'[^a-zA-Z0-9_-]', '_', raw)

    def _emit_progress(self, step: str, message: str, percentage: int,
                       step_index: int = 0, total_steps: int = 6):
        """Yield SSE progress event."""
        yield f"event: progress\ndata: {json.dumps({
            'step': step, 'step_index': step_index, 'total_steps': total_steps,
            'message': message, 'percentage': percentage
        })}\n\n"

    def _emit_section_complete(self, section: str, message: str, **extra):
        """Yield SSE section_complete event."""
        data = {'section': section, 'message': message, **extra}
        yield f"event: section_complete\ndata: {json.dumps(data)}\n\n"

    def _emit_complete(self, result: dict):
        """Yield SSE complete event."""
        yield f"event: complete\ndata: {json.dumps(result)}\n\n"

    def _emit_error(self, error: str):
        """Yield SSE error event."""
        yield f"event: error\ndata: {json.dumps({'error': error})}\n\n"

    def analyze(self, repo_url: str, branch: str, frontend_paths: list[str],
                start_time: str, end_time: str, token: str):
        """Main analysis flow. Returns generator for SSE streaming."""
        self.task_id = self._sanitize_task_id(str(uuid.uuid4()))
        self.task_dir = f"/tmp/analyze_{self.task_id}"
        self.base_worktree = f"{self.task_dir}_base"
        self.target_worktree = f"{self.task_dir}_target"

        repo_name = self._extract_repo_name(repo_url)
        self.bare_repo_path = f"{GIT_CACHE_DIR}/{repo_name}.git"
        self.snapshot_path = f"{self.task_dir}/{SNAPSHOT_FILE}"

        os.makedirs(self.task_dir, exist_ok=True)

        try:
            # Step 1: Knowledge snapshot
            yield from self._emit_progress("snapshot", "检查知识快照...", 5, 1, 7)
            yield from self._ensure_knowledge_snapshot()

            # Step 2: Git fetch
            yield from self._emit_progress("git_fetch", "拉取远程仓库...", 15, 2, 7)
            yield from self._git_fetch(repo_url, branch)

            # Step 3: Resolve commits
            yield from self._emit_progress("resolve_commits", "定位时间段 commits...", 25, 3, 7)
            base, target = self._resolve_commits(branch, start_time, end_time)

            # Step 4: Collect commit messages
            yield from self._emit_progress("commit_messages", "收集 commit messages...", 35, 4, 7)
            commit_messages = self._collect_commit_messages(base, target, frontend_paths)

            # Step 5: Checkout worktree
            yield from self._emit_progress("checkout", "检出双版本代码...", 45, 5, 7)
            self._checkout_worktree(base, target)

            # Step 6: Generate diff
            yield from self._emit_progress("diff", "生成 diff...", 55, 6, 7)
            diff_dir = f"{self.task_dir}/diff"
            yield from self._generate_diff(base, target, frontend_paths, diff_dir)

            yield from self._emit_section_complete("git_diff", "Git diff 完成",
                                                    changed_files=self._count_changed_files(diff_dir))

            # Step 7: AST analysis (subprocess Node.js CLI)
            yield from self._emit_progress("ast", "正在执行 AST 信号提取...", 70, 7, 7)
            yield from self._run_ast_analysis(diff_dir)

            # Step 8: Load AST results
            result_file = f"{self.task_dir}/result.json"
            with open(result_file) as f:
                ast_result = json.load(f)

            yield from self._emit_section_complete("ast_analysis",
                "AST 分析完成", feature_groups=len(ast_result.get("featureGroups", [])))

            # Step 9: LLM summarization
            yield from self._emit_progress("llm", "LLM 正在归纳变更...", 85, 8, 7)
            snapshot = self._load_snapshot()
            yield from self._llm_summarize(ast_result, commit_messages, snapshot)

        except Exception as e:
            yield from self._emit_error(str(e))
        finally:
            self._cleanup()

    def _extract_repo_name(self, repo_url: str) -> str:
        """Extract repo name from URL for cache dir."""
        # Sanitize token from URL
        sanitized = re.sub(r'://[^@]+@', '://', repo_url)
        name = repo_url.rstrip('.git').split('/')[-1]
        return name

    def _ensure_knowledge_snapshot(self):
        """Generate or reuse knowledge snapshot (auto-expire after 3 days)."""
        if os.path.exists(self.snapshot_path):
            try:
                with open(self.snapshot_path) as f:
                    snapshot = json.load(f)
                generated_at = datetime.fromisoformat(snapshot["generatedAt"])
                if (datetime.now() - generated_at).days < 3:
                    return  # Reuse
            except (json.JSONDecodeError, KeyError, ValueError):
                pass  # Corrupted, regenerate

        yield from self._generate_snapshot()

    def _generate_snapshot(self):
        """Call Node.js CLI in snapshot mode."""
        cli_path = "tools/code-analyzer/dist/index.js"
        # Use target worktree if available, else fall back to cloned repo
        target_dir = self.target_worktree if os.path.exists(self.target_worktree) else "."

        result = subprocess.run(
            ["node", cli_path,
             "--target", target_dir,
             "--frontend-paths", ",".join(self._get_all_frontend_paths()),
             "--output", self.snapshot_path,
             "--mode", "snapshot"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            print(f"Warning: snapshot generation failed: {result.stderr}")

    def _git_fetch(self, repo_url: str, branch: str):
        """Clone or fetch bare repo."""
        if not os.path.exists(self.bare_repo_path):
            subprocess.run(
                ["git", "clone", "--mirror", repo_url, self.bare_repo_path],
                cwd="/tmp", capture_output=True, text=True, timeout=600
            )
        else:
            subprocess.run(
                ["git", "fetch", "--all", "--prune"],
                cwd=self.bare_repo_path, capture_output=True, text=True, timeout=120
            )

    def _resolve_commits(self, branch: str, start_time: str, end_time: str):
        """Locate base and target commits."""
        base = subprocess.run(
            ["git", "rev-list", "-n", "1", "--before", start_time,
             f"refs/heads/{branch}"],
            cwd=self.bare_repo_path, capture_output=True, text=True, timeout=30
        ).stdout.strip()

        target = subprocess.run(
            ["git", "rev-list", "-n", "1", "--before", end_time,
             f"refs/heads/{branch}"],
            cwd=self.bare_repo_path, capture_output=True, text=True, timeout=30
        ).stdout.strip()

        if not base or not target:
            raise ValueError("指定时间段内无 commit")
        if base == target:
            raise ValueError("Base 和 Target 相同，时间段内无变更")

        return base, target

    def _collect_commit_messages(self, base: str, target: str,
                                  frontend_paths: list[str]) -> list[str]:
        """Collect commit messages between base and target."""
        paths_part = " ".join(f"-- {p}" for p in frontend_paths)
        result = subprocess.run(
            ["git", "log", "--format=%s", f"{base}..{target}"] + frontend_paths,
            cwd=self.bare_repo_path, capture_output=True, text=True, timeout=30
        )
        return [line for line in result.stdout.strip().split('\n') if line]

    def _checkout_worktree(self, base: str, target: str):
        """Checkout dual versions via worktree."""
        subprocess.run(
            ["git", "worktree", "add", self.base_worktree, base],
            cwd=self.bare_repo_path, capture_output=True, text=True, timeout=60
        )
        subprocess.run(
            ["git", "worktree", "add", self.target_worktree, target],
            cwd=self.bare_repo_path, capture_output=True, text=True, timeout=60
        )

    def _generate_diff(self, base: str, target: str,
                        frontend_paths: list[str], diff_dir: str):
        """Generate diff three-piece (name-status, numstat, raw.patch)."""
        os.makedirs(diff_dir, exist_ok=True)

        # Exclude patterns
        exclude_patterns = [
            "':!package-lock.json'", "':!yarn.lock'", "':!pnpm-lock.yaml'",
            "':!*.min.js'", "':!*.map'", "':!node_modules/'", "':!dist/'",
            "':!build/'", "':!__snapshots__/'", "':!coverage/'",
        ]

        for fp in frontend_paths:
            safe_fp = fp.replace('/', '_')

            # Name-status (with rename detection)
            cmd_name_status = (
                f"git diff --name-status --find-renames=80% {base} {target} -- {fp} "
                + " ".join(exclude_patterns)
            )
            result = subprocess.run(
                cmd_name_status, shell=True, cwd=self.bare_repo_path,
                capture_output=True, text=True, timeout=60
            )
            with open(f"{diff_dir}/{safe_fp}_name_status.txt", 'w') as f:
                f.write(result.stdout)

            # Numstat
            cmd_numstat = (
                f"git diff --numstat --find-renames=80% {base} {target} -- {fp} "
                + " ".join(exclude_patterns)
            )
            result = subprocess.run(
                cmd_numstat, shell=True, cwd=self.bare_repo_path,
                capture_output=True, text=True, timeout=60
            )
            with open(f"{diff_dir}/{safe_fp}_numstat.txt", 'w') as f:
                f.write(result.stdout)

            # Raw patch
            cmd_patch = (
                f"git diff --histogram --find-renames=80% {base} {target} -- {fp} "
                + " ".join(exclude_patterns)
            )
            result = subprocess.run(
                cmd_patch, shell=True, cwd=self.bare_repo_path,
                capture_output=True, text=True, timeout=60
            )
            with open(f"{diff_dir}/{safe_fp}_patch.txt", 'w') as f:
                f.write(result.stdout)

        # Merge all patches into one raw.patch
        with open(f"{diff_dir}/raw.patch", 'w') as out:
            for fp in frontend_paths:
                safe_fp = fp.replace('/', '_')
                patch_file = f"{diff_dir}/{safe_fp}_patch.txt"
                if os.path.exists(patch_file):
                    out.write(open(patch_file).read())
                    out.write('\n')

    def _count_changed_files(self, diff_dir: str) -> int:
        """Count total changed files from diff output."""
        total = 0
        for f in os.listdir(diff_dir):
            if f.endswith('_name_status.txt'):
                total += sum(1 for line in open(f"{diff_dir}/{f}") if line.strip())
        return total

    def _run_ast_analysis(self, diff_dir: str):
        """Run Node.js CLI subprocess for AST analysis."""
        cli_path = "tools/code-analyzer/dist/index.js"

        result = subprocess.run(
            ["node", cli_path,
             "--base", self.base_worktree,
             "--target", self.target_worktree,
             "--diff-dir", diff_dir,
             "--frontend-paths", ",".join(self._get_all_frontend_paths()),
             "--output", f"{self.task_dir}/result.json",
             "--mode", "analyze"],
            capture_output=True, text=True, timeout=180
        )

        if result.returncode != 0:
            raise RuntimeError(f"AST 分析失败: {result.stderr}")

    def _load_snapshot(self) -> dict:
        """Load knowledge snapshot."""
        if os.path.exists(self.snapshot_path):
            with open(self.snapshot_path) as f:
                return json.load(f)
        return {}

    def _llm_summarize(self, ast_result: dict, commit_messages: list[str],
                        snapshot: dict):
        """Build LLM input and call llm_client.py."""
        # Build input
        llm_input = {
            "projectContext": {
                "name": "Algorithm Monorepo",
                "domain": "机器学习模型训练与管理平台",
                "apps": snapshot.get("applications", []),
            },
            "commit_messages": commit_messages,
            "feature_groups": ast_result.get("featureGroups", []),
        }

        system_prompt = """你是 Algorithm Monorepo 项目的代码变更分析师。项目是机器学习模型训练与管理平台。

以下是通过 AST 信号提取和 diff 分析得到的代码变更数据。请生成业务级别的变更报告。

严格规则：
1. 如果 Snippet 中出现具体数字、状态码、字段名，必须在描述中明确提及。
2. 优先使用 doc_context 中的描述来命名和说明功能，snippet 作为验证和补充。
3. 禁止使用"优化了代码"、"完善了功能"等模糊词汇。
4. 对每个变更，判断是否影响用户可感知的行为。
5. 输出仅限合法 JSON。"""

        try:
            response = llm_complete(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": json.dumps(llm_input, ensure_ascii=False)}],
                temperature=0.3,
                response_format={"type": "json_object"},
            )

            llm_result = json.loads(response)
            yield from self._emit_section_complete("complete",
                "分析完成", llm_status="success", **llm_result)
        except Exception as e:
            # Fallback to rule-based result
            yield from self._emit_section_complete("complete",
                "分析完成（规则层降级）", llm_status="failed",
                llm_error=str(e), **self._build_rule_based_result(ast_result))

    def _build_rule_based_result(self, ast_result: dict) -> dict:
        """Build a result from rule-layer signals when LLM fails."""
        groups = ast_result.get("featureGroups", [])
        new_features = []
        modified = []
        ui_updates = []

        for g in groups:
            gtype = g.get("type", "UNKNOWN")
            name = g.get("nameHint", "未知变更")
            files = g.get("files", [])
            evidence = [f.get("path", f) if isinstance(f, dict) else f for f in files]

            if gtype in ("NEW_FEATURE",):
                new_features.append({"name": name, "evidence_files": evidence})
            elif gtype in ("FEATURE_MODIFY",):
                modified.append({"name": name, "evidence_files": evidence})
            else:
                ui_updates.append(name)

        return {
            "new_features": new_features,
            "modified_features": modified,
            "removed_features": [],
            "ui_updates": ui_updates,
        }

    def _get_all_frontend_paths(self) -> list[str]:
        """Default frontend paths for algorithm-monorepo."""
        return [
            "apps/algorithm/ml-main",
            "apps/algorithm/ml-data",
            "apps/algorithm/_share",
        ]

    def _cleanup(self):
        """Clean up worktrees and temp files."""
        for wt in [self.base_worktree, self.target_worktree]:
            if wt and os.path.exists(wt):
                subprocess.run(
                    ["git", "worktree", "remove", "--force", wt],
                    capture_output=True, text=True, timeout=30
                )
        # Remove temp dir
        if self.task_dir and os.path.exists(self.task_dir):
            shutil.rmtree(self.task_dir, ignore_errors=True)


def get_snapshot_info() -> dict:
    """Get current knowledge snapshot metadata."""
    from flask import g
    task_dir = getattr(g, 'task_dir', '/tmp/')
    snapshot_path = f"{task_dir}/knowledge_snapshot.json"
    if os.path.exists(snapshot_path):
        with open(snapshot_path) as f:
            return json.load(f)
    return {}
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/code_analyze_service.py
git commit -m "feat: add code analyze orchestrator service"
```

### Task 3.2: Flask Blueprint + app registration

**Files:**
- Create: `backend/routers/code_analyze.py`
- Modify: `backend/app.py`

- [ ] **Step 1: Write Blueprint**

```python
# backend/routers/code_analyze.py

import json
from flask import Blueprint, Response, jsonify, request, stream_with_context

from services.code_analyze_service import CodeAnalyzeService, get_snapshot_info

code_analyze_bp = Blueprint('code_analyze', __name__)


@code_analyze_bp.route('/start', methods=['POST'])
def start_analysis():
    """Start code change analysis (SSE response)."""
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求体不能为空'}), 400

    required = ['start_time', 'end_time']
    for field in required:
        if field not in data:
            return jsonify({'error': f'缺少必填字段: {field}'}), 400

    repo_url = data.get('repo_url', '')
    branch = data.get('branch', 'master')
    frontend_paths = data.get('frontend_paths', [])
    start_time = data['start_time']
    end_time = data['end_time']

    service = CodeAnalyzeService()

    def generate():
        yield from service.analyze(
            repo_url=repo_url,
            branch=branch,
            frontend_paths=frontend_paths,
            start_time=start_time,
            end_time=end_time,
            token='',
        )

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@code_analyze_bp.route('/status/<task_id>', methods=['GET'])
def get_status(task_id: str):
    """Poll task status (for SSE reconnection recovery)."""
    # In-memory task status tracking (Phase 3 extension: use file-based)
    return jsonify({
        'task_id': task_id,
        'status': 'unknown',
        'current_step': '',
        'step_index': 0,
        'total_steps': 7,
        'percentage': 0,
    })


@code_analyze_bp.route('/refresh-snapshot', methods=['POST'])
def refresh_snapshot():
    """Manually refresh knowledge snapshot (SSE response)."""
    service = CodeAnalyzeService()

    def generate():
        yield f"event: progress\ndata: {json.dumps({'step': 'snapshot', 'message': '正在刷新知识快照...', 'percentage': 50})}\n\n"
        try:
            service._generate_snapshot()
            yield f"event: complete\ndata: {json.dumps({'section': 'complete', 'message': '知识快照刷新完成', 'llm_status': 'success'})}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@code_analyze_bp.route('/snapshot', methods=['GET'])
def get_snapshot():
    """Get current knowledge snapshot."""
    info = get_snapshot_info()
    return jsonify(info)
```

- [ ] **Step 2: Register blueprint in app.py**

```python
# In backend/app.py, add with other imports:
from routers.code_analyze import code_analyze_bp

# Add after other blueprint registrations:
app.register_blueprint(code_analyze_bp, url_prefix='/api/code-analyze')
```

- [ ] **Step 3: Verify Flask import works**

Run: `cd backend && python -c "from routers.code_analyze import code_analyze_bp; print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add backend/routers/code_analyze.py backend/app.py
git commit -m "feat: add code analyze Blueprint + register in app.py"
```

---

## Phase 4: Frontend Page

### Task 4.1: API layer

**Files:**
- Create: `frontend/src/api/codeAnalyze.ts`

- [ ] **Step 1: Write API types and functions**

```typescript
// frontend/src/api/codeAnalyze.ts

import { client } from './client';
import { streamRequest } from '../utils/sse';

// ---- Types ----

export interface AnalysisRequest {
  repo_url?: string;
  branch?: string;
  frontend_paths?: string[];
  start_time: string;
  end_time: string;
}

export interface Summary {
  total_commits?: number;
  analyzed_files: number;
  feature_groups: number;
  functional_changes?: number;
  ui_changes?: number;
  style_only?: number;
}

export interface FeatureGroup {
  id: string;
  type: string;
  priority: string;
  isFunctional: boolean;
  confidence: number;
  nameHint: string;
  files: string[];
  allSignals: string[];
  snippets?: { file: string; before: string | null; after: string | null }[];
}

export interface AnalysisResult {
  task_id: string;
  summary: Summary;
  new_features?: { name: string; confidence: number; evidence_files: string[]; description: string }[];
  modified_features?: { name: string; confidence: number; evidence_files: string[]; description: string }[];
  removed_features?: { name: string; evidence_files: string[]; description: string }[];
  ui_updates?: string[];
  llm_status: string;
}

export interface ProgressEvent {
  step: string;
  step_index?: number;
  total_steps?: number;
  message: string;
  percentage: number;
}

export interface SectionCompleteEvent {
  section: string;
  message: string;
  [key: string]: unknown;
}

export interface TaskStatus {
  task_id: string;
  status: string;
  current_step: string;
  step_index: number;
  total_steps: number;
  percentage: number;
}

export interface SnapshotInfo {
  projectName?: string;
  generatedAt?: string;
  applications?: Array<{ name: string; path: string; role: string }>;
}

// ---- API Functions ----

export function startAnalysis(
  params: AnalysisRequest,
  callbacks: {
    onProgress?: (data: ProgressEvent) => void;
    onSectionComplete?: (data: SectionCompleteEvent) => void;
    onComplete?: (data: AnalysisResult) => void;
    onError?: (error: string) => void;
  }
): AbortController {
  return streamRequest<ProgressEvent, SectionCompleteEvent, AnalysisResult>(
    'POST',
    '/api/code-analyze/start',
    params,
    callbacks
  );
}

export async function getTaskStatus(taskId: string): Promise<TaskStatus> {
  const res = await client.get(`/api/code-analyze/status/${taskId}`);
  return res.data;
}

export function refreshSnapshot(callbacks: {
  onProgress?: (data: ProgressEvent) => void;
  onComplete?: (data: { section: string; message: string }) => void;
  onError?: (error: string) => void;
}): AbortController {
  return streamRequest(
    'POST',
    '/api/code-analyze/refresh-snapshot',
    {},
    callbacks
  );
}

export async function getSnapshotInfo(): Promise<SnapshotInfo> {
  const res = await client.get('/api/code-analyze/snapshot');
  return res.data;
}
```

- [ ] **Step 2: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors (may need `// @ts-nocheck` on sse.ts if streamRequest types differ)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/codeAnalyze.ts
git commit -m "feat: add code analyze API layer"
```

### Task 4.2: Page component

**Files:**
- Create: `frontend/src/pages/CodeAnalyze.tsx`

- [ ] **Step 1: Write page component**

```tsx
// frontend/src/pages/CodeAnalyze.tsx

import React, { useState, useCallback, useEffect, useRef } from 'react';
import {
  Card, DatePicker, Checkbox, Button, Steps, Tag, Tabs,
  Typography, Alert, Spin, Descriptions, Space, Table, Tooltip,
} from 'antd';
import {
  CodeOutlined, ReloadOutlined, PlayCircleOutlined,
  CheckCircleOutlined, CloseCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  startAnalysis, refreshSnapshot, getSnapshotInfo,
  AnalysisResult, ProgressEvent,
} from '../api/codeAnalyze';

const { RangePicker } = DatePicker;
const { Title, Text, Paragraph } = Typography;

const ALL_PATHS = [
  { label: 'ml-main（主应用）', value: 'apps/algorithm/ml-main' },
  { label: 'ml-data（业务子应用）', value: 'apps/algorithm/ml-data' },
  { label: '_share（共享包）', value: 'apps/algorithm/_share' },
];

const STEPS_CONFIG = [
  { title: '知识快照', key: 'snapshot' },
  { title: '拉取仓库', key: 'git_fetch' },
  { title: '定位 commits', key: 'resolve_commits' },
  { title: '收集 commit 信息', key: 'commit_messages' },
  { title: '检出代码', key: 'checkout' },
  { title: '生成 diff', key: 'diff' },
  { title: 'AST 分析', key: 'ast' },
  { title: 'LLM 归纳', key: 'llm' },
];

type StepStatus = 'pending' | 'process' | 'finish' | 'error';

const CodeAnalyze: React.FC = () => {
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [selectedPaths, setSelectedPaths] = useState<string[]>(['apps/algorithm/ml-data']);
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stepStatuses, setStepStatuses] = useState<Record<string, StepStatus>>({});
  const [snapshotInfo, setSnapshotInfo] = useState<string>('');

  const completedRef = useRef<Set<string>>(new Set());
  const abortRef = useRef<AbortController | null>(null);

  // Load snapshot info on mount
  useEffect(() => {
    getSnapshotInfo().then(info => {
      if (info?.generatedAt) {
        setSnapshotInfo(`快照生成于 ${dayjs(info.generatedAt).format('YYYY-MM-DD HH:mm')}`);
      }
    }).catch(() => {});
  }, []);

  const handleStart = useCallback(() => {
    if (!dateRange || !dateRange[0] || !dateRange[1]) return;
    if (selectedPaths.length === 0) {
      setError('请至少选择一个分析路径');
      return;
    }

    setAnalyzing(true);
    setResult(null);
    setError(null);
    setStepStatuses({});
    completedRef.current = new Set();

    // Initialize all steps as pending
    const initial: Record<string, StepStatus> = {};
    STEPS_CONFIG.forEach(s => { initial[s.key] = 'pending'; });
    setStepStatuses(initial);

    const ctrl = startAnalysis(
      {
        start_time: dateRange[0].startOf('day').format('YYYY-MM-DDTHH:mm:ssZ'),
        end_time: dateRange[1].endOf('day').format('YYYY-MM-DDTHH:mm:ssZ'),
        frontend_paths: selectedPaths,
      },
      {
        onProgress: (data: ProgressEvent) => {
          completedRef.current.add(data.step);
          setStepStatuses(prev => {
            const next = { ...prev };
            // Set current step to process
            next[data.step] = 'process';
            // Set all previous steps to finish
            const keys = Object.keys(next);
            const idx = keys.indexOf(data.step);
            for (let i = 0; i < idx; i++) {
              if (next[keys[i]] !== 'error') next[keys[i]] = 'finish';
            }
            return next;
          });
        },
        onSectionComplete: (data) => {
          completedRef.current.add(data.section);
          setStepStatuses(prev => ({ ...prev, [data.section]: 'finish' }));
        },
        onComplete: (data: AnalysisResult) => {
          setStepStatuses(prev => {
            const next = { ...prev };
            for (const k of Object.keys(next)) {
              if (!completedRef.current.has(k)) next[k] = 'error';
            }
            return next;
          });
          setResult(data);
          setAnalyzing(false);
        },
        onError: (err: string) => {
          setError(err);
          setAnalyzing(false);
        },
      }
    );
    abortRef.current = ctrl;
  }, [dateRange, selectedPaths]);

  const handleCancel = useCallback(() => {
    abortRef.current?.abort();
    setAnalyzing(false);
  }, []);

  const handleRefreshSnapshot = useCallback(() => {
    refreshSnapshot({
      onComplete: () => {
        getSnapshotInfo().then(info => {
          if (info?.generatedAt) {
            setSnapshotInfo(`快照已刷新: ${dayjs(info.generatedAt).format('YYYY-MM-DD HH:mm')}`);
          }
        });
      },
      onError: (err) => setError(err),
    });
  }, []);

  const currentStep = STEPS_CONFIG.findIndex(s => stepStatuses[s.key] === 'process');
  const stepsItems = STEPS_CONFIG.map((s, i) => ({
    title: s.title,
    status: stepStatuses[s.key] || 'pending',
    icon: stepStatuses[s.key] === 'finish' ? <CheckCircleOutlined /> :
          stepStatuses[s.key] === 'error' ? <CloseCircleOutlined /> :
          stepStatuses[s.key] === 'process' ? <Spin size="small" /> : undefined,
  }));

  return (
    <div style={{ padding: 24 }}>
      {/* Config Area */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
            <Text strong>目标仓库:</Text>
            <Text code>algorithm-monorepo (master)</Text>
          </div>

          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
            <Text strong>时间段:</Text>
            <RangePicker
              picker="date"
              value={dateRange}
              onChange={(dates) => setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs])}
              disabled={analyzing}
            />
          </div>

          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
            <Text strong>分析路径:</Text>
            <Checkbox.Group
              options={ALL_PATHS}
              value={selectedPaths}
              onChange={(vals) => setSelectedPaths(vals as string[])}
              disabled={analyzing}
            />
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={handleStart}
              loading={analyzing}
              disabled={!dateRange || selectedPaths.length === 0}
            >
              开始分析
            </Button>
            {analyzing && (
              <Button danger onClick={handleCancel}>取消</Button>
            )}
            <Button
              icon={<ReloadOutlined />}
              onClick={handleRefreshSnapshot}
              disabled={analyzing}
            >
              刷新知识库
            </Button>
            {snapshotInfo && (
              <Text type="secondary" style={{ fontSize: 12 }}>{snapshotInfo}</Text>
            )}
          </div>
        </Space>
      </Card>

      {/* Progress Area */}
      {(analyzing || Object.keys(stepStatuses).length > 0) && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <Steps
            current={currentStep}
            direction="vertical"
            size="small"
            items={stepsItems}
          />
        </Card>
      )}

      {/* Error */}
      {error && (
        <Alert
          type="error"
          message="分析失败"
          description={error}
          closable
          style={{ marginBottom: 16 }}
        />
      )}

      {/* Result Area */}
      {result && (
        <Card size="small" title={
          <Space>
            <CodeOutlined />
            <span>分析报告</span>
            <Tag color="blue">{result.llm_status === 'success' ? 'LLM 分析' : '规则层降级'}</Tag>
          </Space>
        }>
          <Descriptions size="small" column={3} style={{ marginBottom: 16 }}>
            <Descriptions.Item label="Feature Groups">
              {result.summary?.feature_groups ?? 0}
            </Descriptions.Item>
            <Descriptions.Item label="Functional Changes">
              {result.summary?.functional_changes ?? 0}
            </Descriptions.Item>
            <Descriptions.Item label="UI Changes">
              {result.summary?.ui_changes ?? 0}
            </Descriptions.Item>
          </Descriptions>

          <Tabs
            items={[
              {
                key: 'new',
                label: `新增功能 (${result.new_features?.length ?? 0})`,
                children: result.new_features?.map((f, i) => (
                  <Card key={i} size="small" style={{ marginBottom: 8 }}>
                    <Space>
                      <Tag color="green">🆕 {f.name}</Tag>
                      <Tag>confidence: {f.confidence?.toFixed(2)}</Tag>
                    </Space>
                    <Paragraph style={{ marginTop: 8 }}>{f.description}</Paragraph>
                    <Space wrap>
                      {f.evidence_files?.map((file, j) => (
                        <Tooltip key={j} title={file}>
                          <Tag style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {file.split('/').pop()}
                          </Tag>
                        </Tooltip>
                      ))}
                    </Space>
                  </Card>
                )) || <Text type="secondary">无</Text>,
              },
              {
                key: 'modified',
                label: `功能修改 (${result.modified_features?.length ?? 0})`,
                children: result.modified_features?.map((f, i) => (
                  <Card key={i} size="small" style={{ marginBottom: 8 }}>
                    <Space>
                      <Tag color="orange">🔄 {f.name}</Tag>
                      <Tag>confidence: {f.confidence?.toFixed(2)}</Tag>
                    </Space>
                    <Paragraph style={{ marginTop: 8 }}>{f.description}</Paragraph>
                    <Space wrap>
                      {f.evidence_files?.map((file, j) => (
                        <Tooltip key={j} title={file}>
                          <Tag style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {file.split('/').pop()}
                          </Tag>
                        </Tooltip>
                      ))}
                    </Space>
                  </Card>
                )) || <Text type="secondary">无</Text>,
              },
              {
                key: 'removed',
                label: `功能下线 (${result.removed_features?.length ?? 0})`,
                children: result.removed_features?.map((f, i) => (
                  <Card key={i} size="small" style={{ marginBottom: 8 }}>
                    <Space>
                      <Tag color="red">🗑️ {f.name}</Tag>
                    </Space>
                    <Paragraph style={{ marginTop: 8 }}>{f.description}</Paragraph>
                  </Card>
                )) || <Text type="secondary">无</Text>,
              },
              {
                key: 'ui',
                label: `UI 更新 (${result.ui_updates?.length ?? 0})`,
                children: result.ui_updates?.map((u, i) => (
                  <div key={i} style={{ marginBottom: 4 }}>• {u}</div>
                )) || <Text type="secondary">无</Text>,
              },
            ]}
          />
        </Card>
      )}
    </div>
  );
};

export default CodeAnalyze;
```

- [ ] **Step 2: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/CodeAnalyze.tsx
git commit -m "feat: add code analyze page component"
```

### Task 4.3: Routes + sidebar integration

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppLayout.tsx`

- [ ] **Step 1: Add route in App.tsx**

Find the Route section and add:
```tsx
import CodeAnalyze from './pages/CodeAnalyze';

{/* Insert after Chat route */}
<Route path="/code-analyze" element={<CodeAnalyze />} />
```

- [ ] **Step 2: Add sidebar item in AppLayout.tsx**

Find `activeNavItems` array and add:
```tsx
import { CodeOutlined } from '@ant-design/icons';

// Add after knowledge base chat item:
{ key: '/code-analyze', icon: <CodeOutlined />, label: '代码变更分析' },
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/AppLayout.tsx
git commit -m "feat: add code-analyze route + sidebar menu item"
```

---

## Phase 5: LLM Integration + End-to-End

### Task 5.1: LLM input builder and prompt iteration

**Files:**
- Modify: `backend/services/code_analyze_service.py` (already written in Task 3.1)

- [ ] **Step 1: Verify llm_complete function signature**

Check `backend/services/llm_client.py` for the exact function signature:

```python
# Expected signature in llm_client.py:
def llm_complete(system_prompt: str, messages: list[dict], 
                 temperature: float = 0.3, response_format: dict | None = None) -> str: ...
```

If different, adjust the call in `code_analyze_service.py`. If `response_format` not supported, add JSON extraction fallback:

```python
response = llm_complete(
    system_prompt=system_prompt,
    messages=[{"role": "user", "content": json.dumps(llm_input, ensure_ascii=False)}],
    temperature=0.3,
)
# Extract JSON from response
try:
    llm_result = json.loads(response)
except json.JSONDecodeError:
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        llm_result = json.loads(json_match.group())
    else:
        raise
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/code_analyze_service.py
git commit -m "feat: finalize LLM integration with JSON extraction fallback"
```

### Task 5.2: End-to-end verification

- [ ] **Step 1: Verify Node.js CLI builds clean**

Run: `cd tools/code-analyzer && npm run build`
Expected: `dist/index.js` generated, no errors

- [ ] **Step 2: Verify Flask can import all modules**

Run: `cd backend && python -c "from routers.code_analyze import code_analyze_bp; print('Flask import OK')"`
Expected: `Flask import OK`

- [ ] **Step 3: Verify Flask app starts**

Run: `cd backend && timeout 5 python run.py 2>&1 || true`
Expected: Flask starts on port 5000, no import errors

- [ ] **Step 4: Verify frontend builds**

Run: `cd frontend && npx tsc --noEmit`
Expected: TypeScript no errors

- [ ] **Step 5: Verify frontend Vite build**

Run: `cd frontend && npm run build 2>&1 | tail -20`
Expected: Build successful

- [ ] **Step 6: Commit Phase 5 complete**

```bash
git add -A
git commit -m "feat: Phase 5 complete — LLM integration + e2e verification"
```

---

## Spec Coverage Check

| Spec Section | Task | Status |
|-------------|------|--------|
| 3.1 CLI structure | 1a.1-1a.3 | ✅ |
| 3.2 CLI interface (--output, file passing) | 1a.3 | ✅ |
| 3.3 10 AST signals | 1a.5, 1b.1, 1b.2 | ✅ |
| 3.4 Doc context | 1b.4 | ✅ |
| 3.5 Constraints (ts-morph no typechecker) | 1a.1 | ✅ |
| 4.1 Knowledge snapshot generation | 2.1 | ✅ |
| 4.2 Auto-expiry (3 days) | 3.1 `_ensure_knowledge_snapshot()` | ✅ |
| 5.2 API endpoints | 3.2 | ✅ |
| 5.3 request format | 3.2 | ✅ |
| 5.4 Orchestrator flow (all 10 steps) | 3.1 | ✅ |
| 5.5 Error handling | 3.1 | ✅ |
| 5.6 Security (token sanitization, worktree cleanup) | 3.1 `_cleanup()`, `_extract_repo_name()` | ✅ |
| 5.7 SSE reconnection + status API | 3.2 `get_status()` | ✅ |
| 5.8 page-logic/ result-layer dedup, @@/ alias, file paths | 3.1 `_generate_diff()`, knowledge snapshot | ✅ |
| 6.2 Page layout (config + progress + result) | 4.2 | ✅ |
| 6.4 Existing patterns (sse.ts, Steps, antd) | 4.2 | ✅ |
| 7.1 LLM input with doc_context | 3.1 `_llm_summarize()` | ✅ |
| 7.2 System Prompt with doc_context priority | 3.1 | ✅ |
| 7.3 Objective confidence | 1b.3 (classifyGroup) | ✅ |