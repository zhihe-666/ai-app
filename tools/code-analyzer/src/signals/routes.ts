// tools/code-analyzer/src/signals/routes.ts
import { HunkInfo, Signal } from '../types.js';

/**
 * Detect route/page changes — supports Umi config routes and JSX Route components.
 */
export function extractRouteSignals(hunk: HunkInfo): Signal[] {
  const signals: Signal[] = [];

  // Detect Umi config route changes (config/config.ts, .umirc.ts)
  if (hunk.file.includes('config/config.ts') || hunk.file.endsWith('.umirc.ts')) {
    for (const line of hunk.addedLines) {
      const pathMatch = line.match(/["']?path["']?\s*:\s*["']([^"']+)["']/);
      if (pathMatch) {
        signals.push({ type: 'NEW_ROUTE', detail: pathMatch[1] });
      }
    }
  }

  // Detect JSX Route component changes
  for (const line of [...hunk.addedLines, ...hunk.removedLines]) {
    const routeMatch = line.match(/<Route[^>]*\spath=["']([^"']+)["']/);
    if (routeMatch) {
      signals.push({ type: 'NEW_ROUTE', detail: `Route path="${routeMatch[1]}"` });
    }
  }

  // Detect NEW_PAGE: new files under pages/ directories
  // Use export default check to distinguish pages from utility modules
  if (hunk.status === 'A') {
    const pageMatch = hunk.file.match(/(\/pages\/.*)\.tsx$/);
    if (pageMatch) {
      // Verify export default via AST if available
      // The astValidator.ts will confirm, so here just do broad match
      signals.push({ type: 'NEW_PAGE', detail: pageMatch[1] });
    }
  }

  return signals;
}