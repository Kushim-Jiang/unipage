<script lang="ts">
  import { resources, bugs, pushNetworkError } from '../../stores/project';
  import * as api from '../api';

  const headers = ['Project Files', 'Font Files', 'Data Files'];
  const rscKeys = ['project', 'font', 'data'];
  const statusLabels = { 0: 'Uncompiled', 1: 'Compile Failed', 2: 'Compiled' };

  $: rsc = $resources;

  /** @type {HTMLInputElement|null} */
  let newFileInput = null;

  async function handleUpload() {
    const input = /** @type {HTMLInputElement} */ (document.createElement('input'));
    input.type = 'file';
    input.multiple = true;
    input.accept = '.tsv,.ttf,.otf';
    input.onchange = async () => {
      const files = input.files;
      if (!files) return;
      for (const file of files) {
        try {
          await api.uploadResource(file);
        } catch (/** @type {any} */ e) { pushNetworkError(e.message); }
      }
      const updated = await api.listResources();
      resources.set(updated);
    };
    input.click();
  }

  /** @param {string} path */
  async function handleDelete(path) {
    if (!confirm(`Delete ${path}?`)) return;
    try {
      await api.deleteResource(path);
      const updated = await api.listResources();
      resources.set(updated);
    } catch (/** @type {any} */ e) { pushNetworkError(e.message); }
  }

  async function handleParseAll() {
    try {
      const r = await api.parseResources();
      bugs.set(r.bugs);
      const updated = await api.listResources();
      resources.set(updated);
    } catch (/** @type {any} */ e) { pushNetworkError(e.message); }
  }
</script>

<div class="resource-tree">
  <div class="toolbar">
    <button on:click={handleUpload}>Import Resource</button>
    <button on:click={handleParseAll}>Parse All</button>
  </div>

  <div class="tree">
    {#each headers as header, idx}
      <details open>
        <summary>{header} ({rsc[rscKeys[idx]]?.length ?? 0})</summary>
        {#if rsc[rscKeys[idx]]?.length > 0}
          {#each rsc[rscKeys[idx]] as item}
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <div class="item" on:contextmenu|preventDefault={() => handleDelete(item[2])} role="listitem">
              <span class="name">{item[0]}</span>
              <span class="status" class:ok={item[1] === 2} class:fail={item[1] === 1}>
                {statusLabels[/** @type {0|1|2} */ (item[1])] ?? 'Unknown'}
              </span>
              <button class="delete" on:click|stopPropagation={() => handleDelete(item[2])} title="Delete">x</button>
            </div>
          {/each}
        {:else}
          <div class="empty">(empty)</div>
        {/if}
      </details>
    {/each}
  </div>
</div>

<style>
  .resource-tree { max-width: 600px; }
  .toolbar { margin-bottom: 0.5rem; display: flex; gap: 0.3rem; }
  .toolbar button { background: #3498db; color: white; border: none; padding: 0.3rem 0.7rem; border-radius: 4px; cursor: pointer; }
  .tree details { margin-bottom: 0.3rem; }
  .tree summary { cursor: pointer; font-weight: bold; padding: 0.3rem; background: #ecf0f1; border-radius: 4px; }
  .item { display: flex; align-items: center; gap: 0.5rem; padding: 0.2rem 0.3rem 0.2rem 1.5rem; font-size: 0.9rem; }
  .name { flex: 1; word-break: break-all; }
  .status { font-size: 0.8rem; color: #7f8c8d; }
  .status.ok { color: #27ae60; }
  .status.fail { color: #e74c3c; }
  .item .delete { opacity: 0; transition: opacity 0.15s; background: transparent; border: none; color: #e74c3c; cursor: pointer; font-size: 1rem; }
  .item:hover .delete { opacity: 1; }
  .empty { padding-left: 1.5rem; color: #bdc3c7; font-size: 0.85rem; }
</style>
