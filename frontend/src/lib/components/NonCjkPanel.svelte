<script lang="ts">
  import { settings, blocks, pushNetworkError } from '../../stores/project';
  import * as api from '../api';

  let generating = false;
  let progressPct = 0;
  let pdfResults: any[] = [];

  $: nonCjkSettings = $settings.filter((s: any) => s.type === 'NL');
  $: nonCjkBlocks = $blocks.filter((b: any) => b.type === 'NL');

  async function generateSingle(setting: any) {
    generating = true;
    try {
      const req: api.NonCjkPdfRequest = {
        block_name: setting.name,
        start_cp: setting.start_cp,
        end_cp: setting.end_cp,
        title_page: !!setting.content.title_page,
        yellow: setting.content.yellow || [],
        purple: setting.content.purple || [],
        draft_mode: !!setting.content.draft_mode,
      };
      const r = await api.generateNonCjkPdf(req);
      pdfResults = [...pdfResults.filter((x: any) => x.block !== setting.name), { ...r, block: setting.name }];
    } catch (e: any) { pushNetworkError(e.message); }
    finally { generating = false; }
  }

  async function generateAll() {
    generating = true; progressPct = 0; pdfResults = [];
    try {
      await api.generateAllNonCjkPdf();
      while (true) {
        await new Promise(r => setTimeout(r, 200));
        const p = await api.pollGenerateProgress();
        progressPct = p.progress;
        if (p.done) {
          pdfResults = p.results || [];
          break;
        }
      }
    } catch (e: any) { pushNetworkError(e.message); }
    finally { generating = false; progressPct = 0; }
  }
</script>

<div class="non-cjk-panel">
  {#if nonCjkBlocks.length === 0 && nonCjkSettings.length === 0}
    <div class="hint">
      <p>No non-CJK blocks detected. Import a <strong>.tsv</strong> data file containing NL and FT sections, then parse resources.</p>
    </div>
  {:else}
    <div class="toolbar">
      <button class="generate-all" disabled={generating || nonCjkSettings.filter((s: any) => s.content.print).length === 0}
              style={generating ? `background-size:${progressPct}% 100%` : ''}
              on:click={generateAll}>
        {generating ? `Generating... ${Math.round(progressPct)}%` : 'Generate All Non-CJK PDFs'}
      </button>
    </div>

    {#each nonCjkSettings.filter((s: any) => s.content.print) as setting}
      <div class="block-row">
        <span class="block-name">{setting.name}</span>
        <button class="generate-btn" disabled={generating} on:click={() => generateSingle(setting)}>
          Generate
        </button>
        {#each pdfResults.filter((r: any) => r.block === setting.name) as result}
          <span class="pdf-result" class:error={result.status === 'error'}>
            {result.status === 'ok' ? '\u2705' : '\u274c'}
          </span>
        {/each}
      </div>
    {/each}
  {/if}
</div>

<style>
  .non-cjk-panel { padding: 0.5rem; }
  .hint { color: #7f8c8d; font-size: 0.85rem; padding: 1rem; text-align: center; }
  .toolbar { margin-bottom: 0.5rem; }
  .generate-all {
    background: #27ae60; color: white; border: none; padding: 0.4rem 1rem;
    border-radius: 4px; cursor: pointer; font-size: 0.9rem;
    background-image: linear-gradient(to right, #2ecc71, #2ecc71);
    background-repeat: no-repeat;
    background-color: #27ae60;
    transition: background-size 0.15s ease-out;
  }
  .generate-all:disabled { opacity: 0.5; cursor: not-allowed; }
  .block-row { display: flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0; font-size: 0.85rem; }
  .block-name { flex: 1; }
  .generate-btn { background: #3498db; color: white; border: none; padding: 0.2rem 0.6rem; border-radius: 4px; cursor: pointer; font-size: 0.8rem; }
  .generate-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .pdf-result { font-size: 0.8rem; }
  .pdf-result.error { color: #c62828; }
</style>
