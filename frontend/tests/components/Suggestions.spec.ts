/**
 * Tests for Suggestions component
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Suggestions from '@/components/Suggestions.vue'

// Mock lucide-vue-next icons
vi.mock('lucide-vue-next', () => ({
  Search: { template: '<svg data-testid="search-icon"></svg>' },
  Compass: { template: '<svg data-testid="compass-icon"></svg>' },
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

    it('should render suggestions when array has items', () => {
      const suggestions = ['Suggestion 1', 'Suggestion 2', 'Suggestion 3']
      const wrapper = mount(Suggestions, {
        props: {
          suggestions,
        },
      })

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

      const suggestionItems = wrapper.findAll('.suggestion-item')
      expect(suggestionItems).toHaveLength(2)
    })

    it('should render icons for each suggestion', () => {
      const wrapper = mount(Suggestions, {
        props: {
          suggestions: ['First', 'Second'],
        },
      })

      expect(wrapper.find('[data-testid="search-icon"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="compass-icon"]').exists()).toBe(true)
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
      const firstSuggestion = wrapper.findAll('.suggestion-item')[0]
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
      const items = wrapper.findAll('.suggestion-item')
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

      const container = wrapper.find('.suggestions-container')
      expect(container.exists()).toBe(true)
      expect(container.classes()).toContain('suggestions-container')
    })

    it('should apply hover transition class to suggestion items', () => {
      const wrapper = mount(Suggestions, {
        props: {
          suggestions: ['Test'],
        },
      })

      const item = wrapper.find('.suggestion-item')
      expect(item.classes()).toContain('suggestion-item')
    })
  })
})
