// tools/code-analyzer/src/knowledge/snapshot.ts
import { Project } from 'ts-morph';
import { KnowledgeSnapshot } from '../types.js';
import fs from 'fs';
import path from 'path';

/**
 * Generate a knowledge snapshot for the target project.
 * Scans: Umi config routes, service/ API modules, pages directory structure.
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

  // Generate timestamp with +08:00 timezone
  const now = new Date();
  const offset = 8 * 60; // +08:00
  const tzSign = offset >= 0 ? '+' : '-';
  const tzHours = String(Math.floor(Math.abs(offset) / 60)).padStart(2, '0');
  const tzMinutes = String(Math.abs(offset) % 60).padStart(2, '0');
  const generatedAt = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}T${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')}${tzSign}${tzHours}:${tzMinutes}`;

  const snapshot: KnowledgeSnapshot = {
    projectName: 'algorithm-monorepo',
    generatedAt,
    applications: [],
    sharedPackages: [],
  };

  for (const fp of frontendPaths) {
    const appPath = path.join(targetPath, fp);
    if (!fs.existsSync(appPath)) {
      console.error(`Warning: path not found: ${appPath}`);
      continue;
    }

    const isShare = fp.includes('_share');
    const isMain = fp.includes('ml-main');

    if (isShare) {
      // Scan all subdirectories under _share for components, utils, etc.
      const components: string[] = [];
      const exports: string[] = [];
      for (const subDir of fs.readdirSync(appPath)) {
        const subPath = path.join(appPath, subDir);
        const stat = fs.statSync(subPath);
        if (stat.isDirectory() && !subDir.startsWith('.')) {
          // Scan recursively for .ts/.tsx files (skip .dumi, .git, node_modules)
          const scanFiles = (dir: string, prefix: string = subDir) => {
            for (const item of fs.readdirSync(dir)) {
              if (item.startsWith('.') || item === 'node_modules') continue;
              const itemPath = path.join(dir, item);
              const itemStat = fs.statSync(itemPath);
              if (itemStat.isDirectory()) {
                scanFiles(itemPath, `${prefix}/${item}`);
              } else if (item.endsWith('.ts') || item.endsWith('.tsx')) {
                if (!item.endsWith('.d.ts') && !item.endsWith('.test.ts') && !item.endsWith('.spec.ts')) {
                  exports.push(`${prefix}/${item.replace(/\.(ts|tsx)$/, '')}`);
                }
              }
            }
          };
          scanFiles(subPath);

          // Components subdir: collect component folders
          if (subDir === 'components' || fs.existsSync(path.join(subPath, 'index.tsx'))) {
            for (const item of fs.readdirSync(subPath)) {
              const itemStat = fs.statSync(path.join(subPath, item));
              if (itemStat.isDirectory()) {
                components.push(item);
              } else if (item.endsWith('.tsx') && !item.endsWith('.d.ts')) {
                components.push(item.replace(/\.tsx$/, ''));
              }
            }
          }
        }
      }
      snapshot.sharedPackages.push({
        name: `@algorithm/${fp.split('/').pop()}`,
        path: fp,
        components,
        exports,
      });
      continue;
    }

    // Resolve appName for template string routes
    let appNameVar = '';
    const pkgJsonPath = path.join(appPath, 'package.json');
    if (fs.existsSync(pkgJsonPath)) {
      try {
        const pkg = JSON.parse(fs.readFileSync(pkgJsonPath, 'utf-8'));
        appNameVar = pkg.appName || '';
      } catch { /* ignore */ }
    }

    // Extract routes from config/config.ts, config/routes.ts, or .umirc.ts
    const routes: { path: string; component?: string; description?: string }[] = [];
    const configCandidates = [
      path.join(appPath, 'config/config.ts'),
      path.join(appPath, 'config/routes.ts'),
      path.join(appPath, '.umirc.ts'),
      path.join(appPath, '.umirc.tsx'),
    ];
    const routeMatcher = /["'`]?path["'`]?\s*:\s*[`"']([^`"']+)[`"']/g;
    for (const configPath of configCandidates) {
      if (fs.existsSync(configPath)) {
        const content = fs.readFileSync(configPath, 'utf-8');
        const routeMatches = content.matchAll(routeMatcher);
        for (const m of routeMatches) {
          // Resolve template variables like ${appName}
          let resolved = m[1];
          if (appNameVar) {
            resolved = resolved.replace(/\$\{appName\}/g, appNameVar);
          }
          if (!routes.some(r => r.path === resolved)) {
            routes.push({ path: resolved });
          }
        }
        // Also extract component references
        const compMatches = content.matchAll(/["']?component["']?\s*:\s*["']([^"']+)["']/g);
        let i = 0;
        for (const m of compMatches) {
          if (i < routes.length) {
            routes[i].component = m[1];
          }
          i++;
        }
      }
    }

    // Scan pages directory for modules
    const modules: string[] = [];
    const pagesDir = path.join(appPath, 'src/pages');
    if (fs.existsSync(pagesDir)) {
      for (const item of fs.readdirSync(pagesDir)) {
        const stat = fs.statSync(path.join(pagesDir, item));
        if (stat.isDirectory()) {
          modules.push(item);
        }
      }
    }

    // Scan service directory for API modules
    const apiModules: { name: string; endpoints: string[] }[] = [];
    const serviceDir = path.join(appPath, 'src/service');
    if (fs.existsSync(serviceDir)) {
      for (const item of fs.readdirSync(serviceDir)) {
        const servicePath = path.join(serviceDir, item);
        const stat = fs.statSync(servicePath);
        if (stat.isDirectory()) {
          const endpoints: string[] = [];
          for (const sub of fs.readdirSync(servicePath)) {
            endpoints.push(sub.replace(/\.(ts|tsx)$/, ''));
          }
          apiModules.push({ name: item, endpoints });
        }
      }
    }

    // Scan components directory
    const components: string[] = [];
    const compDir = path.join(appPath, 'src/components');
    if (fs.existsSync(compDir)) {
      for (const item of fs.readdirSync(compDir)) {
        components.push(item.replace(/\.(ts|tsx)$/, ''));
      }
    }

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