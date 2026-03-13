import { ref, computed, onScopeDispose } from 'vue'

export interface SkillEventData {
  skill_id: string
  skill_name: string
  action: 'activated' | 'deactivated' | 'matched'
  reason: string
  tools_affected?: string[]
  timestamp: string
}

export function useSkillEvents() {
  const activeSkills = ref<Map<string, SkillEventData>>(new Map())
  const recentNotifications = ref<SkillEventData[]>([])

  const activeSkillList = computed(() => Array.from(activeSkills.value.values()))
  const timeoutIds: ReturnType<typeof setTimeout>[] = []

  function handleSkillEvent(event: SkillEventData) {
    if (event.action === 'activated' || event.action === 'matched') {
      activeSkills.value.set(event.skill_id, event)
      recentNotifications.value.push(event)
      const timeoutId = setTimeout(() => {
        const idx = recentNotifications.value.indexOf(event)
        if (idx >= 0) recentNotifications.value.splice(idx, 1)
        // Remove this timeout from tracking
        const tidx = timeoutIds.indexOf(timeoutId)
        if (tidx >= 0) timeoutIds.splice(tidx, 1)
      }, 4000)
      timeoutIds.push(timeoutId)
    } else if (event.action === 'deactivated') {
      activeSkills.value.delete(event.skill_id)
    }
  }

  function reset() {
    activeSkills.value.clear()
    recentNotifications.value = []
    // Clear pending timeouts on reset
    timeoutIds.forEach(clearTimeout)
    timeoutIds.length = 0
  }

  // Clear pending timeouts when the composable's effect scope is disposed
  onScopeDispose(() => {
    timeoutIds.forEach(clearTimeout)
    timeoutIds.length = 0
  })

  return {
    activeSkills,
    activeSkillList,
    recentNotifications,
    handleSkillEvent,
    reset,
  }
}
