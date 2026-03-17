<template>
  <div class="skill-file-tree">
    <SkillFileTreeNode
      v-for="(item, key) in tree"
      :key="key"
      :name="String(key)"
      :item="item"
      :depth="0"
      :selected-path="selectedPath"
      @select="handleSelect"
    />
  </div>
</template>

<script setup lang="ts">
import type { SkillPackageFileTree } from '@/types/message'
import SkillFileTreeNode from './SkillFileTreeNode.vue'

interface Props {
  tree: SkillPackageFileTree
  selectedPath?: string
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'select', path: string): void
}>()

const handleSelect = (path: string) => {
  emit('select', path)
}
</script>

<style scoped>
.skill-file-tree {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px;
}
</style>
