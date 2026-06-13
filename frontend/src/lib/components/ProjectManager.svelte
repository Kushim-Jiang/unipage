<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import * as api from '../api';
  import { projectInfo } from '../../stores/project';

  const dispatch = createEventDispatcher();

  /** @type {'new'|'open'|null} */
  let mode = null;
  let projectName = '';
  let loading = false;
  /** @type {string|null} */
  let error = null;
  let fileInput;

  async function handleCreate() {
    if (!projectName) return;
    loading = true; error = null;
    try {
      const r = await api.createProject(projectName, '');
      projectInfo.set(/** @type {any} */ ({ project_name: projectName, project_dir: '', project_file: r.project_file }));
      dispatch('loaded');
    } catch (/** @type {any} */ e) { error = e.message; }
    finally { loading = false; mode = null; }
  }

  function triggerFilePicker() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      loading = true; error = null;
      try {
        const text = await file.text();
        const data = JSON.parse(text);
        const r = await api.loadProject(data);
        projectInfo.set(r.basic_info);
        dispatch('loaded');
      } catch (/** @type {any} */ e) { error = e.message; }
      finally { loading = false; mode = null; }
    };
    input.click();
  }
</script>

<div class="project-manager">
  {#if mode === null}
    <button on:click={() => mode = 'new'}>New Project</button>
    <button on:click={triggerFilePicker}>Open Project</button>
  {:else if mode === 'new'}
    <div class="form">
      <input bind:value={projectName} placeholder="Project name" disabled={loading} />
      <button on:click={handleCreate} disabled={loading || !projectName}>Create</button>
      <button on:click={() => mode = null} disabled={loading}>Cancel</button>
    </div>
  {/if}

  {#if error}<div class="error">{error}</div>{/if}
  {#if loading}<div class="loading">Processing…</div>{/if}
</div>

<style>
  .project-manager { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
  .form { display: flex; gap: 0.3rem; flex-wrap: wrap; }
  .form input { padding: 0.3rem; border: 1px solid #bdc3c7; border-radius: 4px; font-size: 0.85rem; }
  .project-manager button, .form button { background: #3498db; color: white; border: none; padding: 0.3rem 0.7rem; border-radius: 4px; cursor: pointer; font-size: 0.85rem; }
  .error { color: #e74c3c; font-size: 0.8rem; width: 100%; }
  .loading { color: #bdc3c7; font-size: 0.8rem; }
</style>
