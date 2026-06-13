<script lang="ts">
  import { onMount } from 'svelte';
  import { projectOpen, projectInfo, resources, blocks, settings, bugs, resetAllStores } from './stores/project';
  import * as api from './lib/api';
  import ProjectManager from './lib/components/ProjectManager.svelte';
  import ResourceTree from './lib/components/ResourceTree.svelte';
  import SettingsPanel from './lib/components/SettingsPanel.svelte';
  import BlockViewer from './lib/components/BlockViewer.svelte';
  import BugPanel from './lib/components/BugPanel.svelte';

  let loading = false;
  let parsing = false;
  let checking = false;
  let generating = false;
  let proofsPassed = false;
  let parsePct = 0;
  let checkPct = 0;
  let progressPct = 0;

  // ── Resizable splitter state ────────────────────────────────
  /** Column widths (pixels): left, center, right */
  let colWidths = [260, 0, 240]; // 0 = flex (auto)
  let dragging: 'h-left' | 'h-right' | 'v-bottom' | null = null;
  let leftWidthSaved = 260;
  let rightWidthSaved = 240;
  let bottomHeight = 80;
  let bottomHeightSaved = 80;
  $: showSettings = colWidths[0] > 0;
  $: showResources = colWidths[2] > 0;
  $: showBottom = bottomHeight > 0;

  function startDrag(splitter: 'h-left' | 'h-right' | 'v-bottom') {
    return (e: MouseEvent) => {
      dragging = splitter;
      document.body.style.cursor = splitter === 'v-bottom' ? 'row-resize' : 'col-resize';
      e.preventDefault();
      const startX = e.clientX;
      const startY = e.clientY;
      const startL = colWidths[0];
      const startR = colWidths[2];
      const startH = bottomHeight;
      const onMove = (ev: MouseEvent) => {
        const d = dragging;
        if (!d) return;
        if (d === 'h-left') {
          colWidths[0] = Math.max(120, Math.min(500, startL + (ev.clientX - startX)));
        } else if (d === 'h-right') {
          colWidths[2] = Math.max(120, Math.min(500, startR - (ev.clientX - startX)));
        } else if (d === 'v-bottom') {
          bottomHeight = Math.max(20, Math.min(400, startH - (ev.clientY - startY)));
        }
        colWidths = [...colWidths];
      };
      const onUp = () => {
        dragging = null;
        document.body.style.cursor = '';
      };
      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp, { once: true });
    };
  }

  onMount(async () => {
    try {
      const status = await api.getProjectStatus();
      if (status.open) await loadProjectData();
    } catch (e: any) {
      console.warn('Backend not available:', e.message);
    }
  });

  async function loadProjectData() {
    loading = true;
    try {
      const [rsc, blk, stg] = await Promise.all([
        api.listResources(), api.listBlocks(), api.listSettings(),
      ]);
      resources.set(rsc);
      blocks.set(blk);
      settings.set(stg);
      projectOpen.set(true);
    } catch { /* error already in BottomBar */ }
    finally { loading = false; }
  }

  async function handleParse() {
    parsing = true; parsePct = 0;
    try {
      await api.startParseResources();
      while (true) {
        await new Promise(r => setTimeout(r, 100));
        const p = await api.pollParseProgress();
        parsePct = p.progress;
        if (p.done) {
          if (p.bugs) bugs.set(p.bugs);
          await loadProjectData();
          break;
        }
      }
    } catch { /* error already in BottomBar */ }
    finally { parsing = false; parsePct = 0; }
  }

  async function handleCheckAll() {
    checking = true; checkPct = 0;
    try {
      await api.startCheckAll();
      while (true) {
        await new Promise(r => setTimeout(r, 100));
        const p = await api.pollCheckProgress();
        checkPct = p.progress;
        if (p.done) {
          if (p.bugs) bugs.set(p.bugs);
          proofsPassed = p.passing_count > 0 && p.bugs?.counts?.errors === 0;
          break;
        }
      }
    } catch { proofsPassed = false; }
    finally { checking = false; checkPct = 0; }
  }

  async function handleGenerateAll() {
    generating = true; progressPct = 0;
    try {
      await api.startGenerateAll();
      // Poll progress until done
      while (true) {
        await new Promise(r => setTimeout(r, 100));
        const p = await api.pollGenerateProgress();
        progressPct = p.progress;
        if (p.done) break;
      }
    } catch { /* error already in BottomBar */ }
    finally { generating = false; progressPct = 0; }
  }

  async function handleClose() {
    try { await api.closeProject(); resetAllStores(); }
    catch { /* error already in BottomBar */ }
  }
</script>

<div class="app">
  <!-- ═══ Top bar: title left, buttons right ═══ -->
  <header>
    <div class="top-row">
      <h1>Unipage</h1>
      <div class="top-buttons">
        {#if !$projectOpen}
          <ProjectManager onloaded={loadProjectData} />
        {:else}
          <span class="project-name">{$projectInfo?.project_name ?? 'Untitled'}</span>
          <button class:parsing disabled={parsing} style={parsing ? `background-size:${parsePct}% 100%` : ''} on:click={handleParse}>Parse Resources</button>
          <button class:checking disabled={checking} class:passed={proofsPassed && !checking} style={checking ? `background-size:${checkPct}% 100%` : ''} on:click={handleCheckAll}>Check Proofs</button>
          <button class:generating style={generating ? `background-size:${progressPct}% 100%` : ''} disabled={generating || !proofsPassed} on:click={handleGenerateAll}>Generate PDF</button>
          <button class="danger" on:click={handleClose}>Close Project</button>
        {/if}
      </div>
    </div>
  </header>

  <!-- ═══ Main area: three columns + bottom panel ═══ -->
  <main>
    {#if $projectOpen}
      <div class="main-area">
        <!-- Content row: horizontal grid for 3 columns -->
        <div class="content-row" style="grid-template-columns:{colWidths[0]}px 4px 1fr 4px {colWidths[2]}px">
          <!-- Left: settings -->
          <div class="col-left" class:collapsed={!showSettings}>
            {#if showSettings}<SettingsPanel />{/if}
          </div>
          <!-- Splitter L/C -->
          <div class="splitter-zone splitter-left">
            <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
            <div class="splitter-h" on:mousedown={startDrag('h-left')} role="separator"></div>
            <button class="collapse-btn" class:collapsed={!showSettings} on:click={() => {
              if (colWidths[0] > 0) {
                leftWidthSaved = colWidths[0];
                colWidths[0] = 0;
              } else {
                colWidths[0] = leftWidthSaved;
              }
              colWidths = [...colWidths];
            }}>
              {showSettings ? '◀' : '▶'}
            </button>
          </div>

          <!-- Center: block viewer -->
          <div class="col-center"><BlockViewer /></div>

          <!-- Splitter C/R -->
          <div class="splitter-zone splitter-right">
            <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
            <div class="splitter-h" on:mousedown={startDrag('h-right')} role="separator"></div>
            <button class="collapse-btn" class:collapsed={!showResources} on:click={() => {
              if (colWidths[2] > 0) {
                rightWidthSaved = colWidths[2];
                colWidths[2] = 0;
              } else {
                colWidths[2] = rightWidthSaved;
              }
              colWidths = [...colWidths];
            }}>
              {showResources ? '▶' : '◀'}
            </button>
          </div>

          <!-- Right: resources -->
          <div class="col-right" class:collapsed={!showResources}>
            {#if showResources}<ResourceTree />{/if}
          </div>
        </div>
      </div>
    {:else if !loading}
      <div class="welcome"><h2>Welcome to Unipage</h2><p>Create or open a project to get started.</p></div>
    {/if}

    <!-- Splitter for bottom bug-bar -->
    <div class="splitter-zone-v">
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <div class="splitter-v" on:mousedown={startDrag('v-bottom')} role="separator"></div>
      <button class="collapse-btn-v" class:collapsed={!showBottom} on:click={() => {
        if (bottomHeight > 0) {
          bottomHeightSaved = bottomHeight;
          bottomHeight = 0;
        } else {
          bottomHeight = bottomHeightSaved;
        }
      }}>
        {showBottom ? '▼' : '▲'}
      </button>
    </div>

    <!-- Bottom: bug panel (always visible) -->
    <div class="bug-bar" style="height:{bottomHeight}px" class:collapsed={!showBottom}><BugPanel /></div>
  </main>
</div>

<style>
  .app { font-family: 'Noto Sans SC', system-ui, sans-serif; height: 100vh; display: flex; flex-direction: column; }

  /* ── Top bar ───────────────────────────── */
  header { background: #2c3e50; color: white; padding: 0.3rem 1rem; flex-shrink: 0; }
  .top-row { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
  h1 { margin: 0; font-size: 1.1rem; white-space: nowrap; }
  .top-buttons { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }
  .project-name { font-weight: bold; font-size: 0.9rem; }
  .top-buttons :global(button) { background: #3498db; color: white; border: none; padding: 0.25rem 0.6rem; border-radius: 4px; cursor: pointer; font-size: 0.8rem; white-space: nowrap; position: relative; }
  .top-buttons :global(button.danger) { background: #e74c3c; }
  .top-buttons :global(button.passed) { background: #27ae60; }
  .top-buttons :global(button:disabled) { opacity: 0.6; cursor: not-allowed; }

  /* ── Real progress fill for in-progress buttons ── */
  .top-buttons :global(button.parsing),
  .top-buttons :global(button.checking) {
    cursor: wait;
    background-image: linear-gradient(to right, #f39c12, #f39c12);
    background-repeat: no-repeat;
    background-color: #3498db;
    transition: background-size 0.15s ease-out;
  }
  .top-buttons :global(button.generating) {
    cursor: wait;
    background-image: linear-gradient(to right, #e67e22, #e67e22);
    background-repeat: no-repeat;
    background-color: #3498db;
    transition: background-size 0.15s ease-out;
  }
  /* ── Main area: flex column, content row is a grid ── */
  main { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
  .main-area { display: flex; flex-direction: column; flex: 1; min-height: 0; }
  .content-row { display: grid; flex: 1; min-height: 0; gap: 0; }

  .col-left { overflow-y: auto; padding: 0.3rem; background: #fafafa; min-width: 0; }
  .col-left.collapsed { padding: 0; overflow: hidden; }
  .col-center { overflow-y: auto; padding: 0.3rem; background: #fff; }
  .col-right { overflow-y: auto; padding: 0.3rem; background: #fafafa; min-width: 0; }
  .col-right.collapsed { padding: 0; overflow: hidden; }

  /* ── Splitter zones ─────────────────────── */
  .splitter-zone { position: relative; display: flex; justify-content: center; }
  .splitter-zone .collapse-btn {
    position: absolute;
    top: 50%;
    z-index: 10;
    background: #fafafa;
    border: 1px solid #bdc3c7;
    border-radius: 4px;
    padding: 0.15rem 0.3rem;
    cursor: pointer;
    font-size: 0.7rem;
    color: #7f8c8d;
    line-height: 1;
    transition: left 0.15s, transform 0.15s;
  }
  .splitter-left .collapse-btn {
    left: auto;
    right: 0;
    transform: translateY(-50%);
  }
  .splitter-left .collapse-btn.collapsed {
    left: 0;
    right: auto;
    transform: translateY(-50%);
    border-radius: 0 4px 4px 0;
    border-left: none;
  }
  .splitter-right .collapse-btn {
    left: 0;
    right: auto;
    transform: translateY(-50%);
  }
  .splitter-right .collapse-btn.collapsed {
    left: auto;
    right: 0;
    transform: translateY(-50%);
    border-radius: 4px 0 0 4px;
    border-right: none;
  }
  .splitter-zone .collapse-btn:hover { background: #ecf0f1; }

  /* ── Splitters ──────────────────────────── */
  .splitter-h { cursor: col-resize; background: #e0e0e0; transition: background 0.15s; height: 100%; flex: 1; }
  .splitter-h:hover { background: #3498db; }

  /* ── Bottom bar splitter (v-splitter + collapse button) ── */
  .splitter-zone-v { position: relative; height: 4px; flex-shrink: 0; }
  .splitter-v { cursor: row-resize; height: 4px; width: 100%; background: #e0e0e0; transition: background 0.15s; }
  .splitter-v:hover { background: #3498db; }
  .splitter-zone-v .collapse-btn-v {
    position: absolute;
    left: 50%;
    z-index: 10;
    background: #fafafa;
    border: 1px solid #bdc3c7;
    border-radius: 4px;
    padding: 0.1rem 0.3rem;
    cursor: pointer;
    font-size: 0.65rem;
    color: #7f8c8d;
    line-height: 1;
    transform: translateX(-50%);
    top: 100%;
    margin-top: -1px;
    border-top: none;
    border-radius: 0 0 4px 4px;
  }
  .splitter-zone-v .collapse-btn-v.collapsed {
    top: auto;
    bottom: 100%;
    margin-top: 0;
    margin-bottom: -1px;
    border-bottom: none;
    border-top: 1px solid #bdc3c7;
    border-radius: 4px 4px 0 0;
  }
  .splitter-zone-v .collapse-btn-v:hover { background: #ecf0f1; }

  /* ── Welcome ─────────────────────────────── */
  .welcome { flex: 1; text-align: center; padding: 4rem 2rem; color: #7f8c8d; }

  /* ── Bottom bug bar ──────────────────────── */
  .bug-bar { flex-shrink: 0; border-top: 1px solid #e0e0e0; background: #fff; overflow: hidden; }
  .bug-bar.collapsed { height: 0 !important; border-top: none; }
</style>
