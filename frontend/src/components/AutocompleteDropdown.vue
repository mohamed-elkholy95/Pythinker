<template>
  <Transition name="autocomplete-fade">
    <div
      v-if="isOpen && items.length > 0"
      class="autocomplete-dropdown"
      :style="dropdownStyle"
      ref="dropdownRef"
    >
      <div class="autocomplete-header">
        <span class="autocomplete-title">Skills</span>
        <button class="manage-link" @click="$emit('manage')">
          Manage <span class="arrow">↗</span>
        </button>
      </div>
      <div class="autocomplete-list" ref="listRef">
        <button
          v-for="(item, index) in items"
          :key="item.id"
          class="autocomplete-item"
          :class="{ selected: index === selectedIndex }"
          @click="$emit('select', item)"
          @mouseenter="$emit('hover', index)"
          :ref="el => setItemRef(el, index)"
        >
          <div class="item-icon-wrapper">
            <component :is="getIcon(item.icon)" :size="18" />
          </div>
          <div class="item-content">
            <div class="item-header">
              <span class="item-label">{{ getDisplayLabel(item.label) }}</span>
              <span v-if="item.type === 'skill'" class="item-badge">Official</span>
            </div>
            <span v-if="item.description" class="item-description">
              {{ truncateDescription(item.description) }}
            </span>
          </div>
        </button>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount, type ComponentPublicInstance } from 'vue';
import type { AutocompleteItem } from '@/composables/useAutocomplete';
import {
  Sparkles,
  Search,
  Code,
  Globe,
  Folder,
  BarChart3,
  FileSpreadsheet,
  TrendingUp,
  Bot,
  Puzzle,
  Trash2,
  HelpCircle,
  Download,
  PenTool,
  Wand2,
  FileText,
  BookOpen,
  Zap,
  Shield,
} from 'lucide-vue-next';

import type { AutocompletePosition } from '@/composables/useAutocomplete';

const props = defineProps<{
  isOpen: boolean;
  items: AutocompleteItem[];
  selectedIndex: number;
  position: AutocompletePosition;
}>();

const emit = defineEmits<{
  (e: 'select', item: AutocompleteItem): void;
  (e: 'hover', index: number): void;
  (e: 'manage'): void;
  (e: 'close'): void;
}>();

const dropdownRef = ref<HTMLElement | null>(null);
const listRef = ref<HTMLElement | null>(null);
const itemRefs = ref<(HTMLElement | null)[]>([]);

// Click outside to close
const handleClickOutside = (event: MouseEvent) => {
  if (props.isOpen && dropdownRef.value && !dropdownRef.value.contains(event.target as Node)) {
    emit('close');
  }
};

onMounted(() => {
  document.addEventListener('click', handleClickOutside);
});

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside);
});

const setItemRef = (el: HTMLElement | ComponentPublicInstance | null, index: number) => {
  if (el) {
    itemRefs.value[index] = el as HTMLElement;
  }
};

// Icon mapping
const iconMap: Record<string, typeof Sparkles> = {
  'sparkles': Sparkles,
  'search': Search,
  'code': Code,
  'globe': Globe,
  'folder': Folder,
  'bar-chart': BarChart3,
  'file-spreadsheet': FileSpreadsheet,
  'trending-up': TrendingUp,
  'bot': Bot,
  'puzzle': Puzzle,
  'trash-2': Trash2,
  'help-circle': HelpCircle,
  'download': Download,
  'pen-tool': PenTool,
  'wand-2': Wand2,
  'file-text': FileText,
  'book-open': BookOpen,
  'zap': Zap,
  'shield': Shield,
};

const getIcon = (iconName?: string) => {
  return iconMap[iconName || 'sparkles'] || Sparkles;
};

// Dropdown is now positioned via CSS (bottom of chatbox-input-area)
const dropdownStyle = computed(() => ({}));

// Get display label without leading slash
const getDisplayLabel = (label: string) => {
  return label.startsWith('/') ? label.slice(1) : label;
};

const truncateDescription = (desc: string, maxLength = 50) => {
  if (desc.length <= maxLength) return desc;
  return desc.slice(0, maxLength) + '...';
};

// Scroll selected item into view
watch(() => props.selectedIndex, async (newIndex) => {
  await nextTick();
  const item = itemRefs.value[newIndex];
  if (item && listRef.value) {
    item.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
});
</script>

<style scoped>
.autocomplete-dropdown {
  position: absolute;
  z-index: 1000;
  width: 360px;
  max-width: calc(100% - 24px);
  background: var(--background-white-main);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  box-shadow: 0 10px 28px var(--shadow-S), 0 2px 6px var(--shadow-XS);
  overflow: hidden;
  /* Position inside chatbox, below the input area */
  top: 52px;
  left: 16px;
}

.autocomplete-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-light);
}

.autocomplete-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.02em;
}

.manage-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-tertiary);
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 6px;
  transition: color 0.15s ease, background-color 0.15s ease;
}

.manage-link:hover {
  color: var(--text-primary);
  background: var(--fill-tsp-white-light);
}

.autocomplete-list {
  max-height: 280px;
  overflow-y: auto;
  padding: 8px;
}

.autocomplete-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  border: none;
  background: transparent;
  border-radius: 10px;
  cursor: pointer;
  transition: background-color 0.12s ease;
  text-align: left;
}

.autocomplete-item:hover,
.autocomplete-item.selected {
  background: var(--fill-tsp-white-main);
}

.item-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  flex-shrink: 0;
  background: var(--fill-tsp-white-main);
  color: var(--text-tertiary);
}

.item-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.item-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.item-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.item-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 6px;
  background: var(--fill-tsp-white-dark);
  color: var(--text-tertiary);
}

.item-description {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Transition */
.autocomplete-fade-enter-active,
.autocomplete-fade-leave-active {
  transition: all 0.15s ease;
}

.autocomplete-fade-enter-from,
.autocomplete-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* Scrollbar */
.autocomplete-list::-webkit-scrollbar {
  width: 6px;
}

.autocomplete-list::-webkit-scrollbar-track {
  background: transparent;
}

.autocomplete-list::-webkit-scrollbar-thumb {
  background: var(--bolt-elements-borderColor);
  border-radius: 3px;
}

.autocomplete-list::-webkit-scrollbar-thumb:hover {
  background: var(--text-quaternary);
}
</style>
