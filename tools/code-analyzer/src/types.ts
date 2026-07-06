// tools/code-analyzer/src/types.ts

export type FileStatus = 'A' | 'M' | 'D';
export type GroupType =
  | 'NEW_FEATURE' | 'FEATURE_MODIFY' | 'FEATURE_REMOVAL'
  | 'INFRA_CHANGE' | 'UI_INTERACTION' | 'STYLE_ONLY'
  | 'REFACTOR' | 'DEPENDENCY_UPDATE' | 'TEXT_CHANGE'
  | 'TYPE_CHANGE' | 'TEST_CHANGE' | 'UNKNOWN';
export type Priority = 'P0' | 'P1' | 'P2' | 'P3' | 'P4';
export type SignalType =
  | 'NEW_ROUTE' | 'NEW_PAGE' | 'API_CALL' | 'STATE_ACTION'
  | 'PERMISSION' | 'HOOK_DEF' | 'EVENT_HANDLER' | 'DATA_MODEL'
  | 'CONFIG_CHANGE' | 'STYLE_ONLY' | 'GENERIC_CHANGE'
  | 'TEXT_CHANGE' | 'TYPE_CHANGE' | 'TEST_CHANGE' | 'UNKNOWN';

export interface Signal {
  type: SignalType;
  detail?: string;
  line?: number;
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