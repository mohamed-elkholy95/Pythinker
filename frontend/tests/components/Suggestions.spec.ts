/**
 * Tests for Suggestions component
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Suggestions from '@/components/Suggestions.vue'

// Mock lucide-vue-next icons
vi.mock('lucide-vue-next', () => ({
  Lightbulb: { template: '<svg data-testid="lightbulb-icon"></svg>' },
  ArrowRight: { template: '<svg data-testid="arrow-right-icon"></svg>' },
}))

describe('Suggestions', () => {
  describe('rendering', () => {
    it('should not render when suggestions array is empty', () => {
      const wrapper = mount(Suggestions, {
        props: {
          suggestions: [],
        },
      })

      expect(wrapper.find('div').exists()).toBe(false)
    })

    it('should render header and suggestions when array has items', () => {
      const suggestions = ['Suggestion 1', 'Suggestion 2', 'Suggestion 3']
      const wrapper = mount(Suggestions, {
        props: {
          suggestions,
        },
      })

      // Check header is rendered
      expect(wrapper.text()).toContain('Suggested follow-ups')

      // Check all suggestions are rendered
      suggestions.forEach((suggestion) => {
        expect(wrapper.text()).toContain(suggestion)
      })
    })

    it('should render correct number of suggestion items', () => {
      const suggestions = ['First', 'Second']
      const wrapper = mount(Suggestions, {
        props: {
          suggestions,
        },
      })

      // Each suggestion item has the cursor-pointer class
      const suggestionItems = wrapper.findAll('.cursor-pointer')
      expect(suggestionItems).toHaveLength(2)
    })

    it('should render icons for each suggestion', () => {
      const wrapper = mount(Suggestions, {
        props: {
          suggestions: ['Test suggestion'],
        },
      })

      expect(wrapper.find('[data-testid="lightbulb-icon"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="arrow-right-icon"]').exists()).toBe(true)
    })
  })

  describe('interactions', () => {
    it('should emit select event with suggestion text when clicked', async () => {
      const suggestions = ['Click me', 'Click me too']
      const wrapper = mount(Suggestions, {
        props: {
          suggestions,
        },
      })

      // Click the first suggestion
      const firstSuggestion = wrapper.findAll('.cursor-pointer')[0]
      await firstSuggestion.trigger('click')

      // Check event was emitted with correct value
      expect(wrapper.emitted()).toHaveProperty('select')
      expect(wrapper.emitted('select')).toHaveLength(1)
      expect(wrapper.emitted('select')![0]).toEqual(['Click me'])
    })

    it('should emit separate events for different suggestions', async () => {
      const suggestions = ['First', 'Second', 'Third']
      const wrapper = mount(Suggestions, {
        props: {
          suggestions,
        },
      })

      // Click all suggestions
      const items = wrapper.findAll('.cursor-pointer')
      await items[0].trigger('click')
      await items[1].trigger('click')
      await items[2].trigger('click')

      // Check all events were emitted
      expect(wrapper.emitted('select')).toHaveLength(3)
      expect(wrapper.emitted('select')![0]).toEqual(['First'])
      expect(wrapper.emitted('select')![1]).toEqual(['Second'])
      expect(wrapper.emitted('select')![2]).toEqual(['Third'])
    })
  })

  describe('styling', () => {
    it('should have correct container classes', () => {
      const wrapper = mount(Suggestions, {
        props: {
          suggestions: ['Test'],
        },
      })

      const container = wrapper.find('.flex.flex-col.w-full')
      expect(container.exists()).toBe(true)
      expect(container.classes()).toContain('rounded-[16px]')
      expect(container.classes()).toContain('overflow-hidden')
    })

    it('should apply hover transition class to suggestion items', () => {
      const wrapper = mount(Suggestions, {
        props: {
          suggestions: ['Test'],
        },
      })

      const item = wrapper.find('.cursor-pointer')
      expect(item.classes()).toContain('transition-colors')
    })
  })
})
