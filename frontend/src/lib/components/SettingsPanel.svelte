<script lang="ts">
  import { settings, pushNetworkError } from '../../stores/project';
  import * as api from '../api';

  const formatLabels = ['Right', 'Left', 'Center'];
  const columnLabels = ['2 cols, 6 glyphs/col', '3 cols, 3 glyphs/col', '4 cols, 2 glyphs/col', '5 cols, 1 glyph/col'];
  const yesNo = ['No', 'Yes'];

  /** Record of selected item keys: "settingName:field:sourceIndex" -> true */
  let selected: Record<string, boolean> = {};
  let lastClickedKey = '';
  /** Reactive mirror -- Svelte 5 tracks this object directly in templates. */
  let selMap: Record<string, boolean> = {};
  $: selMap = selected;

  function selKey(setting: any, field: string, si?: number): string {
    return `${setting.name}:${field}:${si ?? ''}`;
  }

  /** Collect all selectable field rows inside the same <details> block. */
  function collectSiblingKeys(targetEl: Element, settingName: string): string[] {
    const details = targetEl.closest('details');
    if (!details) return [];
    const rows = details.querySelectorAll('.field');
    const keys: string[] = [];
    for (const row of rows) {
      const k = row.getAttribute('data-selkey');
      if (k && k.startsWith(settingName)) keys.push(k);
    }
    return keys;
  }

  function toggleSelect(e: MouseEvent, setting: any, field: string, si?: number) {
    const k = selKey(setting, field, si);

    if (e.shiftKey && lastClickedKey) {
      const el = (e.currentTarget as HTMLElement);
      const siblings = collectSiblingKeys(el, setting.name);
      const idxA = siblings.indexOf(lastClickedKey);
      const idxB = siblings.indexOf(k);
      if (idxA !== -1 && idxB !== -1) {
        const lo = Math.min(idxA, idxB);
        const hi = Math.max(idxA, idxB);
        for (let i = lo; i <= hi; i++) selected[siblings[i]] = true;
      }
    } else if (e.ctrlKey || e.metaKey) {
      if (selected[k]) delete selected[k];
      else selected[k] = true;
    } else {
      selected = { [k]: true };
    }
    lastClickedKey = k;
    selected = { ...selected }; // trigger reactivity
  }

  /** Cycle a single item, then batch-update any other selected items. */
  async function cycle(setting: any, field: string, forward: boolean, sourceIndex?: number) {
    const k = selKey(setting, field, sourceIndex);
    const seen = new Set<string>();
    const batch: Array<{ name: string; field: string; si?: number }> = [];
    for (const sk of [k, ...Object.keys(selected)]) {
      if (seen.has(sk)) continue;
      seen.add(sk);
      const parts = sk.split(':');
      const sn = parts[0];
      const sf = parts[1];
      const ssi = parts[2] !== '' ? Number(parts[2]) : undefined;
      batch.push({ name: sn, field: sf, si: ssi });
    }

    try {
      const results: Record<string, any> = {};
      for (const item of batch) {
        const r = setting.type === 'NL'
          ? await api.cycleNonCjkOption(item.name, item.field, forward)
          : await api.cycleOption(item.name, item.field, forward, item.si);
        results[item.name] = r.setting;
      }
      settings.update(s => s.map(st => results[st.name] ?? st));
    } catch (e: any) { pushNetworkError(e.message); }
  }

  /** Validate and save the starting page number. */
  async function handlePageStart(setting: any, e: Event) {
    const input = e.target as HTMLInputElement;
    const raw = input.value.trim();
    const num = parseInt(raw, 10);
    if (isNaN(num) || num < 1 || num !== parseFloat(raw)) {
      input.value = String(setting.content.chart_page_base ?? 1);
      return;
    }
    try {
      const r = await api.setNonCjkPageStart(setting.name, num);
      settings.update(s => s.map(st => st.name === r.setting.name ? r.setting : st));
    } catch (err: any) { pushNetworkError(err.message); }
  }

  function fieldValue(setting: any, idx: number) {
    const v = setting.content[['print', 'column', 'format', 'title'][idx]];
    if (idx === 0 || idx === 3) return yesNo[v];
    if (idx === 1) return columnLabels[v] ?? '';
    if (idx === 2) return formatLabels[v] ?? '';
    return '';
  }

  function isNL(setting: any): boolean { return setting.type === 'NL'; }
</script>

<div class="settings-panel">
  {#each $settings as setting}
    <details open>
      <summary>{setting.name} [{setting.type}]</summary>
      <div class="fields">
        {#if isNL(setting)}
          <!-- Non‑CJK fields -->
          {#each ['Print', 'Title Page', 'Draft Mode'] as label, idx}
            {@const field = ['print', 'title_page', 'draft_mode'][idx]}
            <div class="field" class:sel={selMap[selKey(setting, field)]} data-selkey={selKey(setting, field)}
                 on:click={(e) => toggleSelect(e, setting, field)}
                 on:keydown={(e) => { if (e.key==='ArrowLeft') { e.preventDefault(); cycle(setting,field,false); } else if (e.key==='ArrowRight') { e.preventDefault(); cycle(setting,field,true); } }}
                 role="option" aria-selected={!!selMap[selKey(setting, field)]} tabindex="0">
              <span class="label">{label}</span>
              <button on:click|stopPropagation={() => cycle(setting, field, false)}>&#9665;</button>
              <span class="value">{setting.content[field] ? 'Yes' : 'No'}</span>
              <button on:click|stopPropagation={() => cycle(setting, field, true)}>&#9655;</button>
            </div>
          {/each}
          <div class="field">
            <span class="label">Start Page</span>
            <input
              class="page-input"
              type="number"
              min="1"
              step="1"
              value={setting.content.chart_page_base ?? 1}
              on:change={(e) => handlePageStart(setting, e)}
            />
          </div>
        {:else}
          <!-- CJK fields -->
          {#each ['Print', 'Columns', 'Format', 'Title page'] as label, idx}
            {@const field = ['print', 'column', 'format', 'title'][idx]}
            <div class="field" class:sel={selMap[selKey(setting, field)]} data-selkey={selKey(setting, field)}
                 on:click={(e) => toggleSelect(e, setting, field)}
                 on:keydown={(e) => { if (e.key==='ArrowLeft') { e.preventDefault(); cycle(setting,field,false); } else if (e.key==='ArrowRight') { e.preventDefault(); cycle(setting,field,true); } }}
                 role="option" aria-selected={!!selMap[selKey(setting, field)]} tabindex="0">
              <span class="label">{label}</span>
              <button on:click|stopPropagation={() => cycle(setting, field, false)}>&#9665;</button>
              <span class="value">{fieldValue(setting, idx)}</span>
              <button on:click|stopPropagation={() => cycle(setting, field, true)}>&#9655;</button>
            </div>
          {/each}
        {/if}
      </div>
    </details>
  {/each}
</div>

<style>
  .settings-panel { min-width: 0; }
  details { margin-bottom: 0.5rem; }
  summary { cursor: pointer; font-weight: bold; padding: 0.3rem; background: #ecf0f1; border-radius: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .fields { padding: 0.5rem 0 0.5rem 1rem; }
  .field { display: flex; align-items: center; gap: 0.3rem; margin-bottom: 0.3rem; font-size: 0.9rem; cursor: default; border-radius: 4px; padding: 0.1rem 0.2rem; transition: background 0.1s; user-select: none; }
  .field.sel { background: #d5e8f7; outline: 1px solid #3498db; }
  .label { min-width: 40px; flex-shrink: 0; color: #2c3e50; }
  .value { flex: 1; text-align: center; color: #7f8c8d; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .field button { flex-shrink: 0; background: transparent; border: 1px solid #bdc3c7; border-radius: 4px; padding: 0.1rem 0.4rem; cursor: pointer; }
  .field button:hover { background: #ecf0f1; }
  .page-input { flex: 1; text-align: center; border: 1px solid #bdc3c7; border-radius: 4px; padding: 0.1rem 0.3rem; font-size: 0.85rem; color: #2c3e50; background: #fff; min-width: 0; }
  .page-input:focus { outline: none; border-color: #3498db; }
</style>
