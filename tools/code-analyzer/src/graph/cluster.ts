import { HunkInfo } from '../types.js';
import { ImportGraph } from './importGraph.js';

export function clusterByImportGraph(
  hunks: HunkInfo[],
  graph: ImportGraph
): HunkInfo[][] {
  const clusters: HunkInfo[][] = [];
  const hunkMap = new Map(hunks.map(h => [h.file, h]));

  const bfsCollect = (start: string, visited: Set<string>): string[] => {
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
      for (const [other, neighbors] of graph.adjacency) {
        if (!visited.has(other) && neighbors.has(curr)) {
          queue.push(other);
        }
      }
    }
    return component;
  };

  const allVisited = new Set<string>();

  // Phase 1: cluster files connected by import graph
  for (const hunk of hunks) {
    if (allVisited.has(hunk.file)) continue;
    const hasEdges = graph.adjacency.has(hunk.file);
    const hasNeighbors = hasEdges && graph.adjacency.get(hunk.file)!.size > 0;

    if (hasNeighbors) {
      const component = bfsCollect(hunk.file, allVisited);
      if (component.length > 0) {
        const clusterHunks = component.map(f => hunkMap.get(f)!).filter(Boolean) as HunkInfo[];
        // Include reverse edges
        for (const [other, neighbors] of graph.adjacency) {
          if (!allVisited.has(other) && component.some(f => neighbors.has(f))) {
            const extra = bfsCollect(other, allVisited);
            extra.forEach(f => {
              const h = hunkMap.get(f);
              if (h && !clusterHunks.includes(h)) clusterHunks.push(h);
            });
          }
        }
        clusters.push(clusterHunks);
      }
    }
  }

  // Phase 2: directory clustering for all remaining files
  const remainingHunks = hunks.filter(h => !allVisited.has(h.file));
  const dirMap = new Map<string, HunkInfo[]>();
  for (const hunk of remainingHunks) {
    const dir = hunk.file.substring(0, hunk.file.lastIndexOf('/'));
    if (!dirMap.has(dir)) dirMap.set(dir, []);
    dirMap.get(dir)!.push(hunk);
  }
  for (const [, hunkGroup] of dirMap) {
    clusters.push(hunkGroup);
  }

  // Phase 3: merge page-logic ↔ pages cross-cluster pairs
  mergePageLogicClusters(clusters, hunkMap);

  // Phase 4: split text-only files (constant.ts, types.ts) from their clusters
  splitTextFileClusters(clusters, hunkMap);

  // If somehow still 0 clusters (shouldn't happen), fallback: each file its own cluster
  if (clusters.length === 0 && hunks.length > 0) {
    for (const hunk of hunks) {
      clusters.push([hunk]);
    }
  }

  return clusters;
}

/**
 * Merge clusters where page-logic/ files correspond to pages/ files.
 * Two files are related if swapping page-logic ↔ pages yields the same path.
 */
function mergePageLogicClusters(clusters: HunkInfo[][], hunkMap: Map<string, HunkInfo>): void {
  const normToClusterIdx = new Map<string, number[]>();

  for (let ci = 0; ci < clusters.length; ci++) {
    const seen = new Set<number>();
    for (const hunk of clusters[ci]) {
      const norm = normalizePageLogicPath(hunk.file);
      if (norm) {
        if (!normToClusterIdx.has(norm)) normToClusterIdx.set(norm, []);
        if (!seen.has(ci)) {
          normToClusterIdx.get(norm)!.push(ci);
          seen.add(ci);
        }
      }
    }
  }

  const merged = new Set<number>();
  const toMerge: number[][] = [];
  for (const [, indices] of normToClusterIdx) {
    if (indices.length >= 2) {
      const root = indices[0];
      if (!merged.has(root)) {
        const group = [root];
        merged.add(root);
        for (const idx of indices.slice(1)) {
          if (!merged.has(idx)) {
            group.push(idx);
            merged.add(idx);
          }
        }
        if (group.length >= 2) toMerge.push(group);
      }
    }
  }

  for (const group of toMerge) {
    const target = clusters[group[0]];
    const seenFiles = new Set(target.map(h => h.file));
    for (const idx of group.slice(1)) {
      for (const hunk of clusters[idx]) {
        if (!seenFiles.has(hunk.file)) {
          target.push(hunk);
          seenFiles.add(hunk.file);
        }
      }
      clusters[idx] = []; // mark as empty
    }
  }

  // Remove empty clusters
  for (let i = clusters.length - 1; i >= 0; i--) {
    if (clusters[i].length === 0) clusters.splice(i, 1);
  }
}

/**
 * Normalize path by swapping page-logic ↔ pages.
 * Returns null if neither pattern exists.
 */
function normalizePageLogicPath(filePath: string): string | null {
  if (filePath.includes('/page-logic/')) {
    return filePath.replace('/page-logic/', '/pages/');
  }
  if (filePath.includes('/pages/')) {
    return filePath.replace('/pages/', '/page-logic/');
  }
  return null;
}

/**
 * Phase 4: split text-only files (constant.ts, types.ts, test files) from clusters.
 * These files usually have no import dependency and are bundled into clusters
 * via directory clustering. Splitting them gives cleaner feature groups.
 */
const TEXT_FILE_PATTERNS = [/\/?(constant|contant)\.ts$/, /\/?types\.ts$/];

function isTextFile(filePath: string): boolean {
  return TEXT_FILE_PATTERNS.some(p => p.test(filePath));
}

function splitTextFileClusters(clusters: HunkInfo[][], hunkMap: Map<string, HunkInfo>): void {
  const newClusters: HunkInfo[][] = [];

  for (let ci = clusters.length - 1; ci >= 0; ci--) {
    const cluster = clusters[ci];

    // Only split clusters with 3+ files — small clusters are tight-knit
    if (cluster.length < 3) continue;

    const textHunks: HunkInfo[] = [];
    const keepHunks: HunkInfo[] = [];

    for (const hunk of cluster) {
      if (isTextFile(hunk.file)) {
        textHunks.push(hunk);
      } else {
        keepHunks.push(hunk);
      }
    }

    // Only split if there are both text and non-text files
    if (textHunks.length > 0 && keepHunks.length > 0) {
      clusters[ci] = keepHunks;
      for (const th of textHunks) {
        newClusters.push([th]);
      }
    }
  }

  for (const nc of newClusters) {
    clusters.push(nc);
  }
}