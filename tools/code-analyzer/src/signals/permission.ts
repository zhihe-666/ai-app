// tools/code-analyzer/src/signals/permission.ts
import { Project, SyntaxKind } from 'ts-morph';
import { HunkInfo, Signal } from '../types.js';

/**
 * Detect permission-related changes using AST nodes.
 * Checks IfStatement/BinaryExpression/ConditionalExpression conditions
 * for references to permission-related variables (role, permission, auth, etc.).
 * This avoids false positives from comments, strings, or variable names.
 */
export function extractPermissionSignals(hunk: HunkInfo, project?: Project): Signal[] {
  const signals: Signal[] = [];
  const permissionKeywords = ['role', 'permission', 'auth', 'isAdmin', 'hasAccess', 'canAccess', 'isAllowed'];

  if (project) {
    try {
      const sourceFile = project.getSourceFile(hunk.file);
      if (sourceFile) {
        // Check IfStatement conditions
        const ifStmts = sourceFile.getDescendantsOfKind(SyntaxKind.IfStatement);
        for (const stmt of ifStmts) {
          const conditionText = stmt.getExpression().getText().toLowerCase();
          const hasPermission = permissionKeywords.some(kw => {
            // Ensure keyword is a standalone identifier, not substring
            const regex = new RegExp(`\\b${kw}\\b`, 'i');
            return regex.test(conditionText);
          });
          if (hasPermission) {
            signals.push({ type: 'PERMISSION', detail: conditionText.slice(0, 100) });
          }
        }

        // Check ConditionalExpression (ternary) conditions
        const ternaryExprs = sourceFile.getDescendantsOfKind(SyntaxKind.ConditionalExpression);
        for (const expr of ternaryExprs) {
          const conditionText = expr.getCondition().getText().toLowerCase();
          const hasPermission = permissionKeywords.some(kw => {
            const regex = new RegExp(`\\b${kw}\\b`, 'i');
            return regex.test(conditionText);
          });
          if (hasPermission) {
            signals.push({ type: 'PERMISSION', detail: conditionText.slice(0, 100) });
          }
        }

        // Check BinaryExpression with === (common pattern: role === 'admin')
        const binExprs = sourceFile.getDescendantsOfKind(SyntaxKind.BinaryExpression);
        for (const expr of binExprs) {
          const leftText = expr.getLeft().getText().toLowerCase();
          const hasPermission = permissionKeywords.some(kw => {
            const regex = new RegExp(`\\b${kw}\\b`, 'i');
            return regex.test(leftText);
          });
          if (hasPermission) {
            signals.push({ type: 'PERMISSION', detail: expr.getText().slice(0, 100) });
          }
        }

        if (signals.length > 0) return signals;
      }
    } catch {
      // fallback to regex
    }
  }

  // Regex fallback
  const permissionKeywordsRe = /\b(role|permission|auth|isAdmin|hasAccess|canAccess|isAllowed)\b/i;
  for (const line of [...hunk.addedLines, ...hunk.removedLines]) {
    if (permissionKeywordsRe.test(line)) {
      signals.push({ type: 'PERMISSION', detail: line.trim().slice(0, 100) });
    }
  }

  return signals;
}