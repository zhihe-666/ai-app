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

  // Core decision tree
  if (signalSet.has('NEW_ROUTE') || signalSet.has('NEW_PAGE')) {
    return { type: 'NEW_FEATURE', priority: 'P0', isFunctional: true };
  }

  if (signalSet.has('TEST_CHANGE')) {
    return { type: 'TEST_CHANGE', priority: 'P4', isFunctional: false };
  }

  if (signalSet.has('TEXT_CHANGE')) {
    return { type: 'TEXT_CHANGE', priority: 'P3', isFunctional: false };
  }

  if (signalSet.has('TYPE_CHANGE')) {
    return { type: 'TYPE_CHANGE', priority: 'P3', isFunctional: false };
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

  if (signalSet.has('GENERIC_CHANGE')) {
    return { type: 'FEATURE_MODIFY', priority: 'P2', isFunctional: true };
  }

  if (signalSet.size === 0 || (signalSet.size === 1 && signalSet.has('STYLE_ONLY'))) {
    return { type: 'STYLE_ONLY', priority: 'P3', isFunctional: false };
  }

  return { type: 'UNKNOWN', priority: 'P4', isFunctional: false };
}