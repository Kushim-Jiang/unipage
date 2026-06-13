<script lang="ts">
  import { settings } from '../../stores/project';
  import * as api from '../api';

  const formatLabels = ['Right', 'Left', 'Center']; // Format alignment
  const columnLabels = ['2 cols, 6 glyphs/col', '3 cols, 3 glyphs/col', '4 cols, 2 glyphs/col', '5 cols, 1 glyph/col']; // Column layout
  const yesNo = ['No', 'Yes'];

  /** @param {any} setting @param {string} field @param {boolean} forward */
  async function cycle(setting, field, forward) {
    try {
      const r = await api.cycleOption(setting.name, field, forward);
      // Update local store
      settings.update(s => s.map(st => st.name === setting.name ? r.setting : st));
    } catch (/** @type {any} */ e) { alert(e.message); }
  }

  /** @param {number} idx */
  function fieldLabel(idx) {
    return ['Print', 'Columns', 'Format', 'Title page'][idx] ?? '';
  }

  /** @param {any} setting @param {number} idx */
  function fieldValue(setting, idx) {
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
          <div class="field">
            <span class="label">{label}</span>
            <button on:click={() => cycle(setting, ['print', 'column', 'format', 'title'][idx], false)}>◁</button>
            <span class="value">{fieldValue(setting, idx)}</span>
            <button on:click={() => cycle(setting, ['print', 'column', 'format', 'title'][idx], true)}>▷</button>
          </div>
        {/each}
        {#if setting.type !== 'V' && setting.type !== 'C'}
          <details>
            <summary>Fonts (12 sources)</summary>
            {#each ['G','H','M','T','K','KP','J','V','GS','UK','UTC','SAT'] as src, idx}
              <div class="field">
                <span class="label">{src}</span>
                <button on:click={() => cycle(setting, 'font', false)}>◁</button>
                <span class="value">{setting.content.font?.[idx]?.[1] ?? '(none)'}</span>
                <button on:click={() => cycle(setting, 'font', true)}>▷</button>
              </div>
            {/each}
          </details>
        {:else}
          <div class="field">
            <span class="label">Font</span>
            <button on:click={() => cycle(setting, 'font', false)}>◁</button>
            <span class="value">{setting.content.font?.[1] ?? '(none)'}</span>
            <button on:click={() => cycle(setting, 'font', true)}>▷</button>
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
  .field { display: flex; align-items: center; gap: 0.3rem; margin-bottom: 0.3rem; font-size: 0.9rem; }
  .label { min-width: 40px; flex-shrink: 0; color: #2c3e50; }
  .value { flex: 1; text-align: center; color: #7f8c8d; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .field button { flex-shrink: 0; background: transparent; border: 1px solid #bdc3c7; border-radius: 4px; padding: 0.1rem 0.4rem; cursor: pointer; }
  .field button:hover { background: #ecf0f1; }
</style>
