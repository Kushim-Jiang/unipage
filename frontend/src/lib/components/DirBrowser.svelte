<script lang="ts">
  import { listDirs } from '../api';

  export let show = false;
  /** Called with the absolute path when user selects a folder. */
  export let onpick: (path: string) => void = () => {};

  let current = '';
  let parent = '';
  let dirs: string[] = [];
  let loading = false;

  $: if (show && !current) {
    loadDir('.');
  }

  async function loadDir(path: string) {
    loading = true;
    try {
      const r = await listDirs(path);
      current = r.current;
      parent = r.parent;
      dirs = r.dirs;
    } catch { dirs = []; }
    finally { loading = false; }
  }

  function enterDir(name: string) {
    loadDir(`${current}\\${name}`);
  }

  function goUp() {
    if (parent && parent !== current) loadDir(parent);
  }

  function select() {
    onpick(current);
    close();
  }

  function close() {
    show = false;
    current = '';
    dirs = [];
  }
</script>

{#if show}
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions a11y_interactive_supports_focus -->
  <div class="overlay" on:click={close} role="dialog" tabindex="-1">
    <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_noninteractive_element_interactions -->
    <div class="dialog" on:click|stopPropagation role="document">
      <div class="header">
        <span class="title">Select folder</span>
        <button class="close-btn" on:click={close}>&#10005;</button>
      </div>
      <div class="path">{current || 'Loading...'}</div>
      <div class="list">
        {#if loading}
          <div class="item disabled">Loading...</div>
        {:else}
          <div class="item up" on:click={goUp}>.. (parent)</div>
          {#each dirs as dir}
            <div class="item dir" on:click={() => enterDir(dir)}>
              &#128193; {dir}
            </div>
          {/each}
          {#if dirs.length === 0}
            <div class="item disabled">(empty)</div>
          {/if}
        {/if}
      </div>
      <div class="footer">
        <button class="btn" on:click={close}>Cancel</button>
        <button class="btn primary" on:click={select} disabled={!current}>Select</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed; inset: 0; z-index: 1000;
    background: rgba(0,0,0,0.35);
    display: flex; align-items: center; justify-content: center;
  }
  .dialog {
    background: #fff; border-radius: 8px;
    width: 480px; max-height: 70vh;
    display: flex; flex-direction: column;
    box-shadow: 0 8px 32px rgba(0,0,0,0.2);
  }
  .header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 0.6rem 1rem; border-bottom: 1px solid #e0e0e0;
  }
  .title { font-weight: bold; font-size: 0.95rem; }
  .close-btn { background: none; border: none; cursor: pointer; font-size: 1rem; color: #7f8c8d; }
  .close-btn:hover { color: #e74c3c; }
  .path {
    padding: 0.3rem 1rem; font-size: 0.78rem; color: #7f8c8d;
    background: #f8f9fa; border-bottom: 1px solid #e0e0e0;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .list { flex: 1; overflow-y: auto; padding: 0.3rem 0; min-height: 120px; }
  .item {
    padding: 0.35rem 1rem; cursor: pointer; font-size: 0.85rem;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .item:hover { background: #ecf0f1; }
  .item.up { color: #3498db; font-style: italic; }
  .item.dir { color: #2c3e50; }
  .item.disabled { color: #bdc3c7; cursor: default; }
  .item.disabled:hover { background: transparent; }
  .footer {
    display: flex; justify-content: flex-end; gap: 0.4rem;
    padding: 0.6rem 1rem; border-top: 1px solid #e0e0e0;
  }
  .btn {
    padding: 0.3rem 0.8rem; border: 1px solid #bdc3c7;
    border-radius: 4px; cursor: pointer; font-size: 0.85rem;
    background: #fff; color: #2c3e50;
  }
  .btn:hover { background: #ecf0f1; }
  .btn.primary { background: #3498db; color: #fff; border-color: #3498db; }
  .btn.primary:hover { background: #2980b9; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
