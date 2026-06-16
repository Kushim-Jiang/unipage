/** API client for the Unipage backend */

const API_BASE = '/api';

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

import { pushNetworkError } from '../stores/project';

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
    const msg = 'F001: Cannot connect to backend.';
    pushNetworkError(msg);
    throw new Error(msg);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail || '';
    // Preserve backend bug codes (B001, C006, etc.) if present
    const msg = detail.match(/^[A-Z]\d{3}:/) ? detail : `F002: HTTP ${res.status}${detail ? ': ' + detail : ''}`;
    pushNetworkError(msg, res.status);
    throw new Error(msg);
  }
  return res.json();
}

function get<T = any>(path: string): Promise<T> { return request('GET', path); }
function post<T = any>(path: string, body?: JsonValue): Promise<T> { return request('POST', path, body); }
function del<T = any>(path: string): Promise<T> { return request('DELETE', path); }

// -- Types ---------------------------------------------------------

export interface ProjectStatus {
  open: boolean;
  basic_info?: {
    project_name: string;
    project_dir: string;
    project_file: string;
  };
}

// -- Project ------------------------------------------------------

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

// -- Resources ----------------------------------------------------

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
  if (!res.ok) {
    const err = await res.json();
    const detail = err.detail || '';
    const msg = detail.match(/^[A-Z]\d{3}:/) ? detail : `F002: HTTP ${res.status}${detail ? ': ' + detail : ''}`;
    pushNetworkError(msg, res.status);
    throw new Error(msg);
  }
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

// -- Blocks -------------------------------------------------------

export function listBlocks() {
  return get<any[]>('/blocks');
}

export function getBlock(name: string) {
  return get<any>(`/blocks/${encodeURIComponent(name)}`);
}

// -- Settings -----------------------------------------------------

export function listSettings() {
  return get<any[]>('/settings');
}

export function cycleOption(name: string, field: string, forward: boolean, sourceIndex?: number) {
  return post<{ status: string; setting: any }>('/settings/cycle', { name, field, forward, source_index: sourceIndex });
}

export function toggleColour(name: string, codepoint: number, colour: string) {
  return post<{ status: string; setting: any }>('/settings/colour-toggle', { name, codepoint, colour });
}

// -- Proof / PDF --------------------------------------------------

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

// -- Non-CJK -----------------------------------------------------

export interface NonCjkPdfRequest {
  block_name: string;
  start_cp: number;
  end_cp: number;
  title_page: boolean;
  yellow: number[];
  purple: number[];
}

export function generateNonCjkPdf(req: NonCjkPdfRequest) {
  return post<{ status: string; pdf_path: string; pages: number }>('/non-cjk/generate-pdf', req as any);
}

export function listNonCjkBlocks() {
  return get<any[]>('/non-cjk/blocks');
}

export function getNonCjkBlock(name: string) {
  return get<any>(`/non-cjk/blocks/${encodeURIComponent(name)}`);
}

export function listNonCjkSettings() {
  return get<any[]>('/non-cjk/settings');
}

export function cycleNonCjkOption(name: string, field: string, forward: boolean) {
  return post<{ status: string; setting: any }>('/non-cjk/settings/cycle', { name, field, forward });
}

export function setNonCjkPageStart(name: string, pageStart: number) {
  return post<{ status: string; setting: any }>('/non-cjk/settings/page-start', { name, page_start: pageStart });
}

export function toggleNonCjkColour(name: string, codepoint: number, colour: string) {
  return post<{ status: string; setting: any }>('/non-cjk/settings/colour-toggle', { name, codepoint, colour });
}

export function generateAllNonCjkPdf() {
  return post<{ status: string; total: number }>('/non-cjk/generate-all');
}

// -- Utils --------------------------------------------------------

export function resolveFolder(name: string) {
  return post<{ path: string }>('/utils/resolve-folder', { name });
}

export function listDirs(path: string) {
  return post<{ current: string; parent: string; dirs: string[] }>('/utils/list-dirs', { path });
}
