<script lang="ts">
  import { settings, pushNetworkError } from '../../stores/project';
  import * as api from '../api';

  const formatLabels = ['Right', 'Left', 'Center'];
  const columnLabels = ['2 cols, 6 glyphs/col', '3 cols, 3 glyphs/col', '4 cols, 2 glyphs/col', '5 cols, 1 glyph/col'];
  const yesNo = ['No', 'Yes'];

  /** Record of selected item keys: "settingName:field:sourceIndex" -> true */
  let selected: Record<string, boolean> = {};
  let lastClickedKey = '';
  /** Reactive mirror — Svelte 5 tracks this object directly in templates. */
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
    // Collect ALL selected items (each uses its own field/si)
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
      // First collect all API responses, then apply store update once
      const results: Record<string, any> = {};
      for (const item of batch) {
        const r = await api.cycleOption(item.name, item.field, forward, item.si);
        results[item.name] = r.setting; // last per-name wins (backend state is cumulative)
      }
      settings.update(s => s.map(st => results[st.name] ?? st));
    } catch (/** @type {any} */ e) { pushNetworkError(e.message); }
  }

  function fieldValue(setting: any, idx: number) {
    const v = setting.content[['print', 'column', 'format', 'title'][idx]];
    if (idx === 0 || idx === 3) return yesNo[v];
    if (idx === 1) return columnLabels[v] ?? '';
    if (idx === 2) return formatLabels[v] ?? '';
    return '';
  }
</script>

<div class="settings-panel">
  {#each $settings as setting}
    <details open>
      <summary>{setting.name} [{setting.type}]</summary>
      <div class="fields">
        {#each ['Print', 'Columns', 'Format', 'Title page'] as label, idx}
          {@const field = ['print', 'column', 'format', 'title'][idx]}
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <div class="field" class:sel={selMap[selKey(setting, field)]} data-selkey={selKey(setting, field)}
               on:click={(e) => toggleSelect(e, setting, field)}
               on:keydown={(e) => { if (e.key==='ArrowLeft') { e.preventDefault(); cycle(setting,field,false); } else if (e.key==='ArrowRight') { e.preventDefault(); cycle(setting,field,true); } }}
               role="option" aria-selected={!!selMap[selKey(setting, field)]} tabindex="0">
            <span class="label">{label}</span>
            <button on:click|stopPropagation={() => cycle(setting, field, false)}>◁</button>
            <span class="value">{fieldValue(setting, idx)}</span>
            <button on:click|stopPropagation={() => cycle(setting, field, true)}>▷</button>
          </div>
        {/each}
        {#if setting.type !== 'V' && setting.type !== 'C'}
          <details>
            <summary>Fonts (12 sources)</summary>
            {#each ['G','H','M','T','K','KP','J','V','GS','UK','UTC','SAT'] as src, idx}
              <!-- svelte-ignore a11y_click_events_have_key_events -->
              <div class="field" class:sel={selMap[selKey(setting, 'font', idx)]} data-selkey={selKey(setting, 'font', idx)}
                   on:click={(e) => toggleSelect(e, setting, 'font', idx)}
                   on:keydown={(e) => { if (e.key==='ArrowLeft') { e.preventDefault(); cycle(setting,'font',false,idx); } else if (e.key==='ArrowRight') { e.preventDefault(); cycle(setting,'font',true,idx); } }}
                   role="option" aria-selected={!!selMap[selKey(setting, 'font', idx)]} tabindex="0">
                <span class="label">{src}</span>
                <button on:click|stopPropagation={() => cycle(setting, 'font', false, idx)}>◁</button>
                <span class="value">{setting.content.font?.[idx]?.[1] ?? '(none)'}</span>
                <button on:click|stopPropagation={() => cycle(setting, 'font', true, idx)}>▷</button>
              </div>
            {/each}
          </details>
        {:else}
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <div class="field" class:sel={selMap[selKey(setting, 'font')]} data-selkey={selKey(setting, 'font')}
               on:click={(e) => toggleSelect(e, setting, 'font')}
               on:keydown={(e) => { if (e.key==='ArrowLeft') { e.preventDefault(); cycle(setting,'font',false); } else if (e.key==='ArrowRight') { e.preventDefault(); cycle(setting,'font',true); } }}
               role="option" aria-selected={!!selMap[selKey(setting, 'font')]} tabindex="0">
            <span class="label">Font</span>
            <button on:click|stopPropagation={() => cycle(setting, 'font', false)}>◁</button>
            <span class="value">{setting.content.font?.[1] ?? '(none)'}</span>
            <button on:click|stopPropagation={() => cycle(setting, 'font', true)}>▷</button>
          </div>
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
</style>
