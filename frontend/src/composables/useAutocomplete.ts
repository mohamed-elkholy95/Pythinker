/**
 * Autocomplete composable for ChatBox.
 *
 * Provides:
 * - Slash command completion (/research, /coding, /browser)
 * - AI-powered text suggestions
 * - Keyboard navigation
 */

import { ref, computed } from 'vue';
import { useSkills } from './useSkills';

export interface AutocompleteItem {
  id: string;
  label: string;
  description?: string;
  icon?: string;
  type: 'skill' | 'command' | 'suggestion';
  value: string;
}

export interface AutocompletePosition {
  top: number;
  left: number;
}

export function useAutocomplete() {
  const { availableSkills } = useSkills();

  // State
  const isOpen = ref(false);
  const items = ref<AutocompleteItem[]>([]);
  const selectedIndex = ref(0);
  const query = ref('');
  const triggerType = ref<'slash' | 'text' | null>(null);
  const position = ref<AutocompletePosition>({ top: 0, left: 0 });
  const cursorPosition = ref(0);

  // Built-in commands
  const builtInCommands: AutocompleteItem[] = [
    {
      id: 'cmd-clear',
      label: '/clear',
      description: 'Clear the conversation',
      icon: 'trash-2',
      type: 'command',
      value: '/clear',
    },
    {
      id: 'cmd-help',
      label: '/help',
      description: 'Show available commands',
      icon: 'help-circle',
      type: 'command',
      value: '/help',
    },
    {
      id: 'cmd-export',
      label: '/export',
      description: 'Export conversation',
      icon: 'download',
      type: 'command',
      value: '/export',
    },
  ];

  // Convert skills to autocomplete items
  const skillItems = computed<AutocompleteItem[]>(() => {
    return availableSkills.value.map((skill) => ({
      id: `skill-${skill.id}`,
      label: `/${skill.id}`,
      description: skill.description,
      icon: skill.icon || 'sparkles',
      type: 'skill' as const,
      value: `/${skill.id}`,
    }));
  });

  // All slash command items
  const allSlashItems = computed(() => [
    ...skillItems.value,
    ...builtInCommands,
  ]);

  /**
   * Filter items based on query
   */
  const filterItems = (searchQuery: string, itemList: AutocompleteItem[]): AutocompleteItem[] => {
    if (!searchQuery) return itemList.slice(0, 8);

    const lowerQuery = searchQuery.toLowerCase();
    return itemList
      .filter(item =>
        item.label.toLowerCase().includes(lowerQuery) ||
        item.description?.toLowerCase().includes(lowerQuery)
      )
      .slice(0, 8);
  };

  /**
   * Detect trigger pattern in text
   */
  const detectTrigger = (text: string, caretPos: number): { type: 'slash' | 'text' | null; query: string; startPos: number } => {
    // Look backwards from caret position to find trigger
    const textBeforeCaret = text.slice(0, caretPos);

    // Check for slash command at start of line or after space
    const slashMatch = textBeforeCaret.match(/(?:^|\s)(\/[\w-]*)$/);
    if (slashMatch) {
      return {
        type: 'slash',
        query: slashMatch[1].slice(1), // Remove the /
        startPos: caretPos - slashMatch[1].length,
      };
    }

    return { type: null, query: '', startPos: caretPos };
  };

  /**
   * Update autocomplete based on input
   */
  const updateAutocomplete = (text: string, caretPos: number, _element?: HTMLElement | null) => {
    const trigger = detectTrigger(text, caretPos);

    if (trigger.type === 'slash') {
      triggerType.value = 'slash';
      query.value = trigger.query;
      cursorPosition.value = trigger.startPos;
      items.value = filterItems(trigger.query, allSlashItems.value);
      selectedIndex.value = 0;
      isOpen.value = items.value.length > 0;
      // Position is now handled by CSS (fixed position in dropdown)
    } else {
      close();
    }
  };

  /**
   * Handle keyboard navigation
   */
  const handleKeydown = (event: KeyboardEvent): boolean => {
    if (!isOpen.value) return false;

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        selectedIndex.value = Math.min(selectedIndex.value + 1, items.value.length - 1);
        return true;

      case 'ArrowUp':
        event.preventDefault();
        selectedIndex.value = Math.max(selectedIndex.value - 1, 0);
        return true;

      case 'Tab':
      case 'Enter':
        if (items.value.length > 0) {
          event.preventDefault();
          return true; // Signal that selection should happen
        }
        return false;

      case 'Escape':
        event.preventDefault();
        close();
        return true;

      default:
        return false;
    }
  };

  /**
   * Get the currently selected item
   */
  const getSelectedItem = (): AutocompleteItem | null => {
    return items.value[selectedIndex.value] || null;
  };

  /**
   * Apply selected item to input
   */
  const applySelection = (text: string, item: AutocompleteItem): { newText: string; newCursorPos: number } => {
    const trigger = detectTrigger(text, cursorPosition.value + query.value.length + 1);
    const beforeTrigger = text.slice(0, trigger.startPos);
    const afterTrigger = text.slice(trigger.startPos + query.value.length + 1);

    const newText = beforeTrigger + item.value + ' ' + afterTrigger.trimStart();
    const newCursorPos = beforeTrigger.length + item.value.length + 1;

    close();

    return { newText, newCursorPos };
  };

  /**
   * Close autocomplete
   */
  const close = () => {
    isOpen.value = false;
    items.value = [];
    selectedIndex.value = 0;
    query.value = '';
    triggerType.value = null;
  };

  /**
   * Select item by index
   */
  const selectItem = (index: number) => {
    selectedIndex.value = index;
  };

  return {
    // State
    isOpen,
    items,
    selectedIndex,
    query,
    triggerType,
    position,

    // Methods
    updateAutocomplete,
    handleKeydown,
    getSelectedItem,
    applySelection,
    selectItem,
    close,
  };
}
