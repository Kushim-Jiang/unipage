<script lang="ts">
  import { blocks, pushNetworkError } from '../../stores/project';
  import * as api from '../api';

  let blockDataMap: Record<string, any> = {};
  let loadingMap: Record<string, boolean> = {};
  let blockOpen: Record<string, boolean> = {};

  async function handleToggle(name: string) {
    if (blockOpen[name]) {
      // opened — load data if not already loaded
      if (!blockDataMap[name]) {
        loadingMap[name] = true;
        loadingMap = { ...loadingMap };
        try {
          const data = await api.getBlock(name);
          blockDataMap[name] = data;
          blockDataMap = { ...blockDataMap };
        } catch (e: any) {
          pushNetworkError(e.message);
        } finally {
          loadingMap[name] = false;
          loadingMap = { ...loadingMap };
        }
      }
    } else {
      // closed — free memory
      delete blockDataMap[name];
      blockDataMap = { ...blockDataMap };
    }
  }

  function formatCp(cp: string) {
    const n = parseInt(cp);
    return `${n} (${n.toString(16).toUpperCase().padStart(4, '0')})`;
  }

  function formatVal(val: any): string {
    const s = JSON.stringify(val, (_k, v) => v === null ? '-' : v);
    return s.replace(/"/g, '');
  }
</script>

<div class="block-viewer">
  {#each $blocks as blk}
    <details bind:open={blockOpen[blk.name]} on:toggle={() => handleToggle(blk.name)}>
      <!-- svelte-ignore a11y_click_events_on_non_interactive_element -->
      <summary>
        {blk.name} <span class="type">({blk.type})</span>
      </summary>
      <div class="block-content">
        {#if loadingMap[blk.name]}
          <div class="loading">Loading…</div>
        {:else if blockDataMap[blk.name]}
          <div class="range-info">
            U+{blockDataMap[blk.name].start_cp?.toString(16).toUpperCase()} – U+{blockDataMap[blk.name].end_cp?.toString(16).toUpperCase()}
          </div>
          <div class="entries">
            {#each Object.entries(blockDataMap[blk.name].content) as [cp, val]}
              {#if cp !== 'names_list'}
                <div class="entry">
                  <span class="cp">{formatCp(cp)}</span>
                  <span class="val">{formatVal(val)}</span>
                </div>
              {/if}
            {/each}
          </div>
        {:else}
          <div class="hint">Click to expand</div>
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
  .entry { padding: 0.2rem 0; border-bottom: 1px solid #f0f0f0; display: flex; gap: 0.5rem; }
  .cp { color: #2c3e50; min-width: 150px; flex-shrink: 0; }
  .val { color: #7f8c8d; word-break: break-all; }
  .loading, .hint { text-align: center; padding: 1rem; color: #7f8c8d; font-size: 0.85rem; }
</style>
