import { ref, computed } from 'vue'
import type { SkillDeliveryContent } from '@/types/message'

// Shared state for skill viewer modal
const isViewerOpen = ref(false)
const currentSkill = ref<SkillDeliveryContent | null>(null)
const selectedFilePath = ref<string>('')

export function useSkillViewer() {
  /**
   * Open the skill viewer modal with a specific skill
   */
  const openViewer = (skill: SkillDeliveryContent) => {
    currentSkill.value = skill
    selectedFilePath.value = ''
    isViewerOpen.value = true

    // Auto-select SKILL.md if available
    const skillMd = skill.files.find(f => f.path === 'SKILL.md')
    if (skillMd) {
      selectedFilePath.value = 'SKILL.md'
    } else if (skill.files.length > 0) {
      selectedFilePath.value = skill.files[0].path
    }
  }

  /**
   * Close the skill viewer modal
   */
  const closeViewer = () => {
    isViewerOpen.value = false
    // Keep skill data for exit animation, clear after
    setTimeout(() => {
      if (!isViewerOpen.value) {
        currentSkill.value = null
        selectedFilePath.value = ''
      }
    }, 300)
  }

  /**
   * Select a file in the viewer
   */
  const selectFile = (path: string) => {
    selectedFilePath.value = path
  }

  /**
   * Get the currently selected file
   */
  const selectedFile = computed(() => {
    if (!currentSkill.value || !selectedFilePath.value) return null
    return currentSkill.value.files.find(f => f.path === selectedFilePath.value) || null
  })

  return {
    isViewerOpen,
    currentSkill,
    selectedFilePath,
    selectedFile,
    openViewer,
    closeViewer,
    selectFile,
  }
}
