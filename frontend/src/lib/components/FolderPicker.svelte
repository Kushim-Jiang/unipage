<script lang="ts">
  import DirBrowser from './DirBrowser.svelte';

  /** A folder-path input with a backend-driven directory browser. */
  export let value: string = '';
  export let placeholder: string = 'Folder path';
  export let disabled: boolean = false;

  let browserOpen = false;

  function onPick(path: string) {
    value = path;
  }
</script>

<DirBrowser bind:show={browserOpen} onpick={onPick} />

<div class="folder-picker">
  <input
    type="text"
    {placeholder}
    {disabled}
    readonly
    bind:value
    class="dir-input"
  />
  <button
    class="pick-btn"
    title="Browse folders..."
    {disabled}
    on:click={() => browserOpen = true}
  >&#128193; Browse</button>
</div>

<style>
  .folder-picker {
    display: flex;
    gap: 0.3rem;
    align-items: center;
    flex: 1;
  }
  .dir-input {
    flex: 1;
    min-width: 160px;
    padding: 0.3rem;
    border: 1px solid #bdc3c7;
    border-radius: 4px;
    font-size: 0.85rem;
  }
  .pick-btn {
    background: #ecf0f1;
    border: 1px solid #bdc3c7;
    border-radius: 4px;
    padding: 0.2rem 0.5rem;
    cursor: pointer;
    font-size: 0.82rem;
    white-space: nowrap;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.2rem;
  }
  .pick-btn:hover {
    background: #dfe6e9;
  }
  .pick-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
