/** API client for the Unipage backend */

const API_BASE = '/api';

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

async function request<T = any>(method: string, path: string, body?: JsonValue): Promise<T> {
  const opts: RequestInit = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== undefined) {
    opts.body = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, opts);
  } catch {
    throw new Error('Cannot connect to backend. Make sure the server is running on port 8001.');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

function get<T = any>(path: string): Promise<T> { return request('GET', path); }
function post<T = any>(path: string, body?: JsonValue): Promise<T> { return request('POST', path, body); }
function del<T = any>(path: string): Promise<T> { return request('DELETE', path); }

// ── Types ─────────────────────────────────────────────────────────

export interface ProjectStatus {
  open: boolean;
  basic_info?: {
    project_name: string;
    project_dir: string;
    project_file: string;
  };
}

// ── Project ──────────────────────────────────────────────────────

export function createProject(name: string, directory: string) {
  return post<{ status: string; project_file: string }>('/project/create', { name, directory, file: '' });
}

export function openProject(path: string) {
  return post<{ status: string; basic_info: any; bugs: any }>('/project/open', path);
}

export function loadProject(data: Record<string, any>) {
  return post<{ status: string; basic_info: any; bugs: any }>('/project/load', data);
}

export function saveProject() {
  return post('/project/save');
}

export function closeProject() {
  return post('/project/close');
}

export function getProjectStatus() {
  return get<ProjectStatus>('/project/status');
}

// ── Resources ────────────────────────────────────────────────────

import type { ResourceMap } from '../stores/project';

export function listResources() {
  return get<ResourceMap>('/resources');
}

export function importResource(path: string) {
  return post('/resources/import', path);
}

export async function uploadResource(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/resources/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

export function deleteResource(path: string) {
  return del(`/resources?path=${encodeURIComponent(path)}`);
}

export function parseResources() {
  return post<{ status: string; bugs: any }>('/resources/parse');
}

export function startParseResources() {
  return post<{ status: string; total: number }>('/resources/parse');
}

export function pollParseProgress() {
  return get<{ progress: number; done: boolean; bugs: any | null }>('/resources/parse-progress');
}

export function parseOneResource(path: string) {
  return get(`/resources/parse-one?path=${encodeURIComponent(path)}`);
}

// ── Blocks ───────────────────────────────────────────────────────

export function listBlocks() {
  return get<any[]>('/blocks');
}

export function getBlock(name: string) {
  return get<any>(`/blocks/${encodeURIComponent(name)}`);
}

// ── Settings ─────────────────────────────────────────────────────

export function listSettings() {
  return get<any[]>('/settings');
}

export function cycleOption(name: string, field: string, forward: boolean) {
  return post<{ status: string; setting: any }>('/settings/cycle', { name, field, forward });
}

export function toggleColour(name: string, codepoint: number, colour: string) {
  return post<{ status: string; setting: any }>('/settings/colour-toggle', { name, codepoint, colour });
}

// ── Proof / PDF ──────────────────────────────────────────────────

export function checkProof(name: string) {
  return post(`/proof/check?name=${encodeURIComponent(name)}`);
}

export function generatePdf(name: string) {
  return post(`/proof/generate?name=${encodeURIComponent(name)}`);
}

export function checkAllProofs() {
  return post<{ status: string; passing_count: number; bugs: any }>('/proof/check-all');
}

export function startCheckAll() {
  return post<{ status: string; total: number }>('/proof/check-all');
}

export function pollCheckProgress() {
  return get<{ progress: number; done: boolean; bugs: any | null; passing_count: number }>('/proof/check-progress');
}

export function generateAllPdfs() {
  return post<{ status: string; results: any[] }>('/proof/generate-all');
}

/** Start PDF generation (runs in background thread). */
export function startGenerateAll() {
  return post<{ status: string; total: number }>('/proof/generate-all');
}

/** Poll current generation progress. */
export function pollGenerateProgress() {
  return get<{ progress: number; done: boolean; results: any[] }>('/proof/generate-progress');
}
