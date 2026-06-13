/** Svelte stores for project state */

import { writable, derived, type Writable, type Readable } from 'svelte/store';

export interface ProjectInfo {
  project_name: string;
  project_dir: string;
  project_file: string;
}

export interface ResourceMap {
  [key: string]: any[][];
  project: any[][];
  block: any[][];
  font: any[][];
  attribute: any[][];
}

export interface BugReport {
  [key: string]: any;
  errors: any[];
  warnings: any[];
  infos: any[];
  counts: { errors: number; warnings: number; infos: number };
}

/** Whether a project is open */
export const projectOpen: Writable<boolean> = writable(false);

/** Basic info of the open project */
export const projectInfo: Writable<ProjectInfo | null> = writable(null);

/** Resource lists grouped by type */
export const resources: Writable<ResourceMap> = writable({ project: [], block: [], font: [], attribute: [] });

/** Parsed block list */
export const blocks: Writable<any[]> = writable([]);

/** Per-block settings */
export const settings: Writable<any[]> = writable([]);

/** Bug/error report */
export const bugs: Writable<BugReport> = writable({
  errors: [], warnings: [], infos: [],
  counts: { errors: 0, warnings: 0, infos: 0 },
});

/** Proof results from check-all */
export const proofs: Writable<any[]> = writable([]);

/** Derived: count of compiled resources */
export const compiledCount: Readable<number> = derived(resources, ($r) => {
  return ($r.block || []).filter((r: any) => r[1] === 2).length +
         ($r.attribute || []).filter((r: any) => r[1] === 2).length;
});

// ── Network errors (connection, HTTP 4xx/5xx) ─────────────────────

export interface NetworkError {
  id: number;
  message: string;
  timestamp: Date;
  status?: number;
}

export const networkErrors: Writable<NetworkError[]> = writable([]);
let _errId = 0;

export function pushNetworkError(message: string, status?: number): void {
  networkErrors.update((arr) => {
    const entry: NetworkError = { id: ++_errId, message, timestamp: new Date(), status };
    return [...arr.slice(-49), entry]; // keep last 50
  });
}

export function clearNetworkErrors(): void {
  networkErrors.set([]);
}

/** Reset all stores (on project close) */
export function resetAllStores(): void {
  projectOpen.set(false);
  projectInfo.set(null);
  resources.set({ project: [], block: [], font: [], attribute: [] });
  blocks.set([]);
  settings.set([]);
  bugs.set({ errors: [], warnings: [], infos: [], counts: { errors: 0, warnings: 0, infos: 0 } });
  proofs.set([]);
}
