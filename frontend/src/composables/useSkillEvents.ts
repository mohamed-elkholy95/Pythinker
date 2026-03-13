import { ref, computed } from 'vue'

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

  function handleSkillEvent(event: SkillEventData) {
    if (event.action === 'activated' || event.action === 'matched') {
      activeSkills.value.set(event.skill_id, event)
      recentNotifications.value.push(event)
      setTimeout(() => {
        const idx = recentNotifications.value.indexOf(event)
        if (idx >= 0) recentNotifications.value.splice(idx, 1)
      }, 4000)
    } else if (event.action === 'deactivated') {
      activeSkills.value.delete(event.skill_id)
    }
  }

  function reset() {
    activeSkills.value.clear()
    recentNotifications.value = []
  }

  return {
    activeSkills,
    activeSkillList,
    recentNotifications,
    handleSkillEvent,
    reset,
  }
}
