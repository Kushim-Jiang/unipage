<script lang="ts">
  import { projectOpen, projectInfo, resources, compiledCount } from '../../stores/project';
</script>

<div class="status-bar">
  <span>
    {#if $projectOpen}
      Project: {$projectInfo?.project_name ?? 'Unknown'}
      | Resources: {($resources.project?.length ?? 0) + ($resources.block?.length ?? 0) + ($resources.font?.length ?? 0) + ($resources.attribute?.length ?? 0)}
      | Compiled: {$compiledCount}
    {:else}
      No project open
    {/if}
  </span>
  <span class="backend">Backend: FastAPI</span>
</div>

<style>
  .status-bar {
    background: #ecf0f1;
    padding: 0.3rem 1rem;
    font-size: 0.8rem;
    color: #7f8c8d;
    display: flex;
    justify-content: space-between;
  }
</style>
