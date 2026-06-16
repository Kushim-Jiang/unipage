<script lang="ts">
  export let tab: 'cjk' | 'noncjk' = 'cjk';

  import { blocks } from '../../stores/project';
  import * as api from '../api';

  let blockDataMap: Record<string, any> = {};
  let loadingMap: Record<string, boolean> = {};

  $: filteredBlocks = $blocks.filter((b: any) => tab === 'noncjk' ? b.type === 'NL' : b.type !== 'NL');

  // Auto-load data sequentially when filteredBlocks change
  let loadedOnce = false;
  $: {
    if (filteredBlocks.length > 0 && !loadedOnce) {
      loadedOnce = true;
      loadAll(filteredBlocks);
    }
  }
  // Reset when tab changes
  $: { tab; loadedOnce = false; blockDataMap = {}; loadingMap = {}; }

  async function loadAll(list: any[]) {
    for (const blk of list) {
      await loadBlock(blk);
    }
  }

  async function loadBlock(blk: any) {
    if (blockDataMap[blk.name]) return;
    loadingMap[blk.name] = true;
    loadingMap = { ...loadingMap };
    try {
      const data = blk.type === 'NL'
        ? await api.getNonCjkBlock(blk.name)
        : await api.getBlock(blk.name);
      blockDataMap[blk.name] = data;
      blockDataMap = { ...blockDataMap };
    } catch {
      // Silently skip — block may not have data yet
    } finally {
      loadingMap[blk.name] = false;
      loadingMap = { ...loadingMap };
    }
  }

  function formatCp(cp: string, isHex: boolean = false) {
    const n = isHex ? parseInt(cp, 16) : parseInt(cp, 10);
    return isNaN(n) ? cp : `U+${n.toString(16).toUpperCase().padStart(4, '0')} (${n})`;
  }

  function formatVal(val: any): string {
    const s = JSON.stringify(val, (_k, v) => v === null ? '-' : v);
    return s.replace(/"/g, '');
  }
</script>

<div class="block-viewer">
  {#each filteredBlocks as blk}
    <details open>
      <summary>
        {blk.name} <span class="type">({blk.type})</span>
      </summary>
      <div class="block-content">
        {#if loadingMap[blk.name]}
          <div class="loading">Loading...</div>
        {:else if blockDataMap[blk.name]}
          <div class="range-info">
            U+{blk.start_cp?.toString(16).toUpperCase().padStart(4, '0')} – U+{blk.end_cp?.toString(16).toUpperCase().padStart(4, '0')}
          </div>
          {#if blk.type === 'NL'}
            <div class="entries nl-entries">
              {#each blockDataMap[blk.name].entries || [] as entry}
                <div class="entry">
                  <span class="cp">{formatCp(entry.codepoint, true)}</span>
                  <span class="name">{entry.name || '<reserved>'}</span>
                  {#if entry.annotations?.length}
                    <span class="annos">
                      {#each entry.annotations as a}
                        <span class="anno">{a.type}: {a.text || a.target_cp || ''}</span>
                      {/each}
                    </span>
                  {/if}
                </div>
              {/each}
              {#if !blockDataMap[blk.name].entries?.length}
                <div class="hint">No entries</div>
              {/if}
            </div>
          {:else}
            <div class="entries">
              {#each Object.entries(blockDataMap[blk.name].content || {}) as [cp, val]}
                {#if cp !== 'names_list'}
                  <div class="entry">
                    <span class="cp">{formatCp(cp, false)}</span>
                    <span class="val">{formatVal(val)}</span>
                  </div>
                {/if}
              {/each}
            </div>
          {/if}
        {:else}
          <div class="loading">Loading...</div>
        {/if}
      </div>
    </details>
  {:else}
    <div class="hint">No blocks</div>
  {/each}
</div>

<style>
  .block-viewer { overflow-y: auto; }
  details { margin-bottom: 0.3rem; }
  summary { cursor: pointer; font-weight: bold; padding: 0.3rem; background: #ecf0f1; border-radius: 4px; font-size: 0.9rem; }
  .type { font-weight: normal; color: #7f8c8d; font-size: 0.8rem; }
  .block-content { padding: 0.5rem 0 0.5rem 0.5rem; }
  .range-info { font-size: 0.8rem; color: #7f8c8d; margin-bottom: 0.3rem; }
  .entries { font-family: monospace; font-size: 0.85rem; }
  .entry { padding: 0.2rem 0; border-bottom: 1px solid #f0f0f0; display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .cp { color: #2c3e50; min-width: 140px; flex-shrink: 0; }
  .name { color: #2c3e50; min-width: 200px; }
  .val { color: #7f8c8d; word-break: break-all; }
  .annos { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .anno { color: #7f8c8d; font-size: 0.8rem; }
  .nl-entries .entry { align-items: baseline; }
  .loading, .hint { text-align: center; padding: 1rem; color: #7f8c8d; font-size: 0.85rem; }
</style>
