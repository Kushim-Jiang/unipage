<script lang="ts">
  import { bugs, networkErrors } from '../../stores/project';

  /** Combine parse bugs + network errors into one flat list sorted by severity */
  $: allEntries = [
    // Parse/check diagnostics (severity: error > warning > info)
    ...($bugs.errors || []).map((b: any) => ({ ...b, _severity: 'error' })),
    ...($bugs.warnings || []).map((b: any) => ({ ...b, _severity: 'warning' })),
    ...($bugs.infos || []).map((b: any) => ({ ...b, _severity: 'info' })),
    // Network errors (always error severity, with NET-XXX code)
    ...$networkErrors.map((ne) => ({
      _severity: 'error' as const,
      code: `NET-${String(ne.id).padStart(3, '0')}`,
      label: ne.message,
      file: ne.status ? `HTTP ${ne.status}` : '',
      detail: '',
    })),
  ];
</script>

<div class="bug-panel">
  <div class="toolbar">
    <span class="title">Diagnostics</span>
    <span class="counts">
      E{$bugs.counts?.errors ?? 0} / W{$bugs.counts?.warnings ?? 0} / I{$bugs.counts?.infos ?? 0}
      {#if $networkErrors.length > 0}
        <span class="net-count">+ NET:{$networkErrors.length}</span>
      {/if}
    </span>
  </div>
  <div class="list">
    {#if allEntries.length > 0}
      {#each allEntries as bug}
        <div class="entry" class:error={bug._severity === 'error'} class:warning={bug._severity === 'warning'}>
          <span class="severity-tag" class:err={bug._severity === 'error'} class:warn={bug._severity === 'warning'}>
            {bug._severity === 'error' ? 'E' : bug._severity === 'warning' ? 'W' : 'I'}
          </span>
          <span class="code">{bug.code}</span>
          <span class="label">{bug.label}</span>
          {#if bug.file}<span class="file">{bug.file}</span>{/if}
          {#if bug.detail}<span class="detail">{bug.detail}</span>{/if}
        </div>
      {/each}
    {:else}
      <div class="empty">No diagnostics.</div>
    {/if}
  </div>
</div>

<style>
  .bug-panel { height: 100%; display: flex; flex-direction: column; min-height: 0; }
  .toolbar { display: flex; align-items: center; justify-content: space-between; padding: 0.2rem 0.5rem; background: #f8f9fa; border-bottom: 1px solid #e0e0e0; font-size: 0.75rem; flex-shrink: 0; }
  .title { font-weight: bold; color: #2c3e50; }
  .counts { color: #95a5a6; }
  .net-count { color: #e74c3c; margin-left: 0.3rem; font-weight: bold; }
  .list { flex: 1; overflow-y: auto; font-size: 0.8rem; min-height: 0; }
  .entry { padding: 0.2rem 0.4rem; border-bottom: 1px solid #f0f0f0; display: flex; align-items: center; gap: 0.3rem; }
  .entry.error { background: #fef0ef; }
  .entry.warning { background: #fef9e7; }
  .severity-tag { display: inline-block; width: 18px; height: 18px; line-height: 18px; text-align: center; border-radius: 3px; font-size: 0.7rem; font-weight: bold; color: #fff; flex-shrink: 0; }
  .severity-tag.err { background: #e74c3c; }
  .severity-tag.warn { background: #f39c12; }
  .severity-tag:not(.err):not(.warn) { background: #3498db; }
  .code { font-family: monospace; font-weight: bold; min-width: 35px; flex-shrink: 0; }
  .label { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .file { color: #7f8c8d; font-size: 0.75rem; flex-shrink: 0; }
  .detail { color: #95a5a6; font-size: 0.75rem; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .empty { text-align: center; padding: 1rem; color: #bdc3c7; }
</style>
