// tools/code-analyzer/src/signals/astValidator.ts
import { Project, SyntaxKind } from 'ts-morph';
import { HunkInfo, Signal } from '../types.js';

/**
 * Central AST validation layer.
 * Receives regex-discovered signals and uses ts-morph AST nodes
 * to filter out false positives.
 *
 * Strategy: each validator function checks one signal type.
 * If the AST cannot confirm the signal, it's removed.
 * If AST parsing fails (file not loaded, parse error), signal is kept (conservative).
 */

const KNOWN_FALSE_POSITIVES = new Set([
  'setTimeout', 'setInterval', 'setAttribute',
]);

export function validateSignals(
  signals: Signal[],
  hunk: HunkInfo,
  project: Project,
): Signal[] {
  const result: Signal[] = [];

  for (const signal of signals) {
    let outcome: 'keep' | 'remove' | 'replace' = 'keep';
    let replacement: Signal | null = null;

    try {
      switch (signal.type) {
        case 'STATE_ACTION': {
          const r = validateStateAction(signal, hunk, project);
          if (r === 'remove') outcome = 'remove';
          break;
        }
        case 'API_CALL': {
          const r = validateApiCall(signal, hunk, project);
          if (r === 'remove') outcome = 'remove';
          break;
        }
        case 'PERMISSION': {
          const r = validatePermission(signal, hunk, project);
          if (r === 'remove') outcome = 'remove';
          break;
        }
        case 'DATA_MODEL': {
          const r = validateDataModel(signal, hunk, project);
          if (r === 'remove') outcome = 'remove';
          break;
        }
        case 'HOOK_DEF': {
          const r = validateHookDef(signal, hunk, project);
          if (r === 'remove') outcome = 'remove';
          break;
        }
        case 'EVENT_HANDLER': {
          const r = validateEventHandler(signal, hunk, project);
          if (r === 'remove') outcome = 'remove';
          break;
        }
        case 'STYLE_ONLY': {
          const r = validateStyleOnly(signal, hunk, project);
          if (r === 'remove') {
            outcome = 'remove';
          } else if (r === 'replace') {
            outcome = 'replace';
            // When a file has code but only STYLE_ONLY signal was detected,
            // replace with GENERIC_CHANGE so the decision tree doesn't classify as pure style
            replacement = { type: 'GENERIC_CHANGE' as any, detail: hunk.file };
          }
          break;
        }
        case 'NEW_PAGE': {
          const r = validateNewPage(signal, hunk, project);
          if (r === 'remove') outcome = 'remove';
          break;
        }
        default:
          outcome = 'keep';
      }
    } catch {
      outcome = 'keep';
    }

    if (outcome === 'keep') {
      result.push(signal);
    } else if (outcome === 'replace' && replacement) {
      result.push(replacement);
    }
    // 'remove': do nothing
  }

  return result;
}

/**
 * Helper: resolve source file from hunk.file (relative path).
 * Direct lookup may fail because project has full absolute paths.
 */
function _getSourceFile(project: Project, relativePath: string) {
  let sf = project.getSourceFile(relativePath);
  if (!sf) {
    for (const s of project.getSourceFiles()) {
      if (s.getFilePath().endsWith(relativePath)) {
        sf = s;
        break;
      }
    }
  }
  return sf;
}

/**
 * STATE_ACTION: verify the matched text is actually a CallExpression,
 * and not a known false positive (setTimeout, setInterval, setAttribute).
 */
function validateStateAction(signal: Signal, hunk: HunkInfo, project: Project): 'keep' | 'remove' {
  const detail = (signal.detail || '').toLowerCase();

  // Exclude known false positives
  for (const fp of KNOWN_FALSE_POSITIVES) {
    if (detail.includes(fp)) return 'remove';
  }

  // Try to find the source file and verify it's a real CallExpression
  const sourceFile = _getSourceFile(project, hunk.file);
  if (!sourceFile) return 'keep'; // conservative

  const callExprs = sourceFile.getDescendantsOfKind(SyntaxKind.CallExpression);
  const matchTarget = signal.detail?.split('(')[0]?.trim();

  for (const ce of callExprs) {
    const exprText = ce.getExpression().getText();
    if (exprText === matchTarget) {
      return 'keep'; // confirmed as real CallExpression
    }
  }

  return 'keep'; // keep by default
}

/**
 * API_CALL: verify api.* calls are actual CallExpressions,
 * and check api import source to distinguish project api from other `api` usages.
 */
function validateApiCall(signal: Signal, hunk: HunkInfo, project: Project): 'keep' | 'remove' {
  const detail = signal.detail || '';

  // fetch() and useRequest() are unambiguous
  if (detail.startsWith('fetch(') || detail.startsWith('useRequest(')) return 'keep';

  // For api.* / request.* calls, verify via AST
  if (detail.includes('api.') || detail.includes('request.')) {
    const sourceFile = _getSourceFile(project, hunk.file);
    if (!sourceFile) return 'keep';

    // Check if 'api' is imported from project's own request module
    const importDecls = sourceFile.getImportDeclarations();
    let hasApiImport = false;
    for (const decl of importDecls) {
      const moduleSpec = decl.getModuleSpecifierValue();
      if (moduleSpec.endsWith('/request') || moduleSpec.endsWith('/api') || moduleSpec === 'axios') {
        hasApiImport = true;
      }
    }

    // If api is not imported from a known request module, this may be a false positive
    // e.g. a variable named `api` used as function parameter
    if (!hasApiImport) {
      // Verify it's actually a CallExpression
      const callExprs = sourceFile.getDescendantsOfKind(SyntaxKind.CallExpression);
      const matchPrefix = detail.split('(')[0]; // "api.get" from "api.get("
      for (const ce of callExprs) {
        if (ce.getExpression().getText().startsWith(matchPrefix)) return 'keep';
      }
      return 'remove'; // not confirmed as real API call
    }
  }

  return 'keep';
}

/**
 * PERMISSION: verify the keyword appears in an IfStatement condition
 * or BinaryExpression (comparison), not in a comment or string.
 */
function validatePermission(signal: Signal, hunk: HunkInfo, project: Project): 'keep' | 'remove' {
  const detail = (signal.detail || '').toLowerCase();
  const permissionKeywords = ['role', 'permission', 'auth', 'isadmin', 'hasaccess', 'canaccess', 'isallowed'];

  const sourceFile = _getSourceFile(project, hunk.file);
  if (!sourceFile) return 'keep';

  // Check all condition contexts
  const conditionTexts: string[] = [];

  try {
    const ifStmts = sourceFile.getDescendantsOfKind(SyntaxKind.IfStatement);
    for (const stmt of ifStmts) {
      conditionTexts.push(stmt.getExpression().getText().toLowerCase());
    }

    const ternaryExprs = sourceFile.getDescendantsOfKind(SyntaxKind.ConditionalExpression);
    for (const expr of ternaryExprs) {
      conditionTexts.push(expr.getCondition().getText().toLowerCase());
    }
  } catch {
    return 'keep'; // conservative
  }

  // If keyword found in any condition, it's a real permission check
  const kw = permissionKeywords.find(k => detail.includes(k));
  if (kw) {
    return conditionTexts.some(ct => ct.includes(kw)) ? 'keep' : 'remove';
  }

  return 'keep';
}

/**
 * DATA_MODEL: verify interface/type/enum is a real declaration.
 * Conservative: only remove if we can confirm it's a false positive (e.g. in a comment/string).
 * The regex `interface|type|enum` is already fairly specific, so keep by default.
 */
function validateDataModel(signal: Signal, hunk: HunkInfo, project: Project): 'keep' | 'remove' {
  const sourceFile = _getSourceFile(project, hunk.file);
  if (!sourceFile) return 'keep';

  try {
    const interfaces = sourceFile.getDescendantsOfKind(SyntaxKind.InterfaceDeclaration);
    const typeAliases = sourceFile.getDescendantsOfKind(SyntaxKind.TypeAliasDeclaration);
    const enums = sourceFile.getDescendantsOfKind(SyntaxKind.EnumDeclaration);

    // If the file has real declarations, signal is confirmed
    if (interfaces.length > 0 || typeAliases.length > 0 || enums.length > 0) return 'keep';

    // No declarations found — could be in a comment or string.
    // Check if the matched line is actually a comment.
    const detail = signal.detail || '';
    if (detail.trim().startsWith('//') || detail.trim().startsWith('*') || detail.trim().startsWith('/*')) {
      return 'remove'; // confirmed false positive (in comment)
    }

    return 'keep'; // conservative: keep if unsure
  } catch {
    return 'keep';
  }
}

/**
 * HOOK_DEF: verify function name starts with "use" and is a real function declaration.
 */
function validateHookDef(signal: Signal, hunk: HunkInfo, project: Project): 'keep' | 'remove' {
  const name = signal.detail || '';
  if (!name.startsWith('use')) return 'remove';

  const sourceFile = _getSourceFile(project, hunk.file);
  if (!sourceFile) return 'keep';

  try {
    // Check FunctionDeclaration
    const funcDecls = sourceFile.getDescendantsOfKind(SyntaxKind.FunctionDeclaration);
    for (const fd of funcDecls) {
      if (fd.getName() === name) return 'keep';
    }

    // Check VariableDeclaration (const useXxx = ...)
    const varDecls = sourceFile.getDescendantsOfKind(SyntaxKind.VariableDeclaration);
    for (const vd of varDecls) {
      if (vd.getName() === name) return 'keep';
    }

    // Not found as real function — but could still be a hook reference
    return 'keep'; // conservative
  } catch {
    return 'keep';
  }
}

/**
 * EVENT_HANDLER: verify the JSX attribute exists as a real JsxAttribute.
 */
function validateEventHandler(signal: Signal, hunk: HunkInfo, project: Project): 'keep' | 'remove' {
  const name = signal.detail || ''; // e.g. "onClick"

  const sourceFile = _getSourceFile(project, hunk.file);
  if (!sourceFile) return 'keep';

  try {
    const jsxAttrs = sourceFile.getDescendantsOfKind(SyntaxKind.JsxAttribute);
    for (const attr of jsxAttrs) {
      if (attr.getNameNode().getText() === name) return 'keep';
    }

    // Could be in a template or string — keep
    return 'keep';
  } catch {
    return 'keep';
  }
}

/**
 * STYLE_ONLY: verify file has no logic code.
 * If the file has function/class/variable declarations, it's NOT style-only.
 * In that case, remove the STYLE_ONLY signal and DON'T add a replacement.
 * The decision tree will classify it based on remaining signals.
 * If no remaining signals, the group will still be STYLE_ONLY, but that's correct
 * because the regex-based extractors didn't find any specific signal.
 */
function validateStyleOnly(signal: Signal, hunk: HunkInfo, project: Project): 'keep' | 'remove' | 'replace' {
  const sourceFile = _getSourceFile(project, hunk.file);
  if (!sourceFile) return 'keep';

  try {
    // Check for non-style declarations
    const funcDecls = sourceFile.getDescendantsOfKind(SyntaxKind.FunctionDeclaration);
    const varDecls = sourceFile.getDescendantsOfKind(SyntaxKind.VariableDeclaration);
    const classDecls = sourceFile.getDescendantsOfKind(SyntaxKind.ClassDeclaration);
    const ifStmts = sourceFile.getDescendantsOfKind(SyntaxKind.IfStatement);
    const callExprs = sourceFile.getDescendantsOfKind(SyntaxKind.CallExpression);

    // If file has functions, variables, classes, or if-statements, it's not style-only
    if (funcDecls.length > 0 || varDecls.length > 0 || classDecls.length > 0 || ifStmts.length > 0) {
      return 'remove'; // remove STYLE_ONLY signal
    }

    // If no declarations, it's truly style-only
    return 'keep';
  } catch {
    return 'keep';
  }
}

/**
 * NEW_PAGE: verify file has an export default component.
 * Note: hunk.file is relative path; project.getSourceFile needs full path.
 * We check by iterating source files and matching the suffix.
 */
function validateNewPage(signal: Signal, hunk: HunkInfo, project: Project): 'keep' | 'remove' {
  // Try to find source file by matching path suffix
  let sourceFile = project.getSourceFile(hunk.file);

  if (!sourceFile) {
    // Try matching by suffix (hunk.file is relative, project has full paths)
    for (const sf of project.getSourceFiles()) {
      if (sf.getFilePath().endsWith(hunk.file)) {
        sourceFile = sf;
        break;
      }
    }
  }

  if (!sourceFile) return 'keep'; // conservative, keep signal

  try {
    const funcDecls = sourceFile.getFunctions().filter(f => f.isDefaultExport());
    const classDecls = sourceFile.getClasses().filter(c => c.isDefaultExport());
    const exportAssignments = sourceFile.getDescendantsOfKind(SyntaxKind.ExportAssignment);
    if (funcDecls.length === 0 && classDecls.length === 0 && exportAssignments.length === 0) {
      return 'remove'; // new file under pages but no export default → not a real page
    }
  } catch {
    return 'keep';
  }

  return 'keep';
}