<template>
  <component :is="iconComponent" class="w-5 h-5 text-[var(--icon-secondary)]" />
</template>

<script setup lang="ts">
import { computed } from 'vue';
import {
  FileText,
  Search,
  Code,
  Globe,
  MessageSquare,
  MessageCircle,
  MessagesSquare,
  MessageSquareDot,
  MessageSquareText,
  MessageSquareMore,
  Mic,
  Terminal,
  Database,
  Layout,
  Cpu,
  BookOpen,
  Palette,
  Settings,
  Download,
  Upload,
  Image,
  Video,
  Calculator,
  Mail,
  ShoppingCart,
  Map,
  Zap,
  Bot,
  BrainCircuit,
  Lightbulb,
  Pen,
  Blocks,
  Puzzle,
  Compass,
  Rocket,
  Target,
  Flame,
  Coffee
} from 'lucide-vue-next';

interface Props {
  title: string;
  sessionId?: string;
}

const props = defineProps<Props>();

// Default icon variants for variety when no keyword matches
const defaultIcons = [
  MessageSquare,
  MessageCircle,
  MessagesSquare,
  MessageSquareDot,
  MessageSquareText,
  MessageSquareMore,
  Bot,
  BrainCircuit,
  Lightbulb,
  Pen,
  Blocks,
  Puzzle,
  Compass,
  Rocket,
  Target,
  Flame,
  Coffee
];

// Simple hash function to get consistent index from string
const hashString = (str: string): number => {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return Math.abs(hash);
};

// Determine icon based on task title keywords
const iconComponent = computed(() => {
  const title = props.title.toLowerCase();

  // AI/ML related
  if (title.includes('ai ') || title.includes('ml ') || title.includes('machine learning') ||
      title.includes('neural') || title.includes('model') || title.includes('llm') ||
      title.includes('gpt') || title.includes('claude') || title.includes('gemini')) {
    return BrainCircuit;
  }

  // Code/Programming
  if (title.includes('code') || title.includes('function') || title.includes('script') ||
      title.includes('program') || title.includes('develop') || title.includes('debug') ||
      title.includes('python') || title.includes('javascript') || title.includes('typescript') ||
      title.includes('react') || title.includes('vue') || title.includes('api')) {
    return Code;
  }

  // Terminal/Shell
  if (title.includes('terminal') || title.includes('shell') || title.includes('command') ||
      title.includes('bash') || title.includes('cli')) {
    return Terminal;
  }

  // File operations
  if (title.includes('file') || title.includes('document') || title.includes('report') ||
      title.includes('pdf') || title.includes('csv') || title.includes('excel')) {
    return FileText;
  }

  // Search/Research
  if (title.includes('search') || title.includes('find') || title.includes('research') ||
      title.includes('look') || title.includes('query')) {
    return Search;
  }

  // Web/Browser
  if (title.includes('web') || title.includes('browser') || title.includes('website') ||
      title.includes('page') || title.includes('scrape') || title.includes('crawl') ||
      title.includes('http') || title.includes('url')) {
    return Globe;
  }

  // Database
  if (title.includes('database') || title.includes('sql') || title.includes('mongo') ||
      title.includes('redis') || title.includes('data')) {
    return Database;
  }

  // Design/UI
  if (title.includes('design') || title.includes('ui') || title.includes('ux') ||
      title.includes('layout') || title.includes('style') || title.includes('css')) {
    return Palette;
  }

  // Frontend/Layout
  if (title.includes('frontend') || title.includes('component') || title.includes('landing')) {
    return Layout;
  }

  // System/CPU
  if (title.includes('system') || title.includes('cpu') || title.includes('memory') ||
      title.includes('performance') || title.includes('optimize')) {
    return Cpu;
  }

  // Documentation/Guide
  if (title.includes('guide') || title.includes('tutorial') || title.includes('learn') ||
      title.includes('study') || title.includes('beginner') || title.includes('overview')) {
    return BookOpen;
  }

  // Settings/Config
  if (title.includes('setting') || title.includes('config') || title.includes('setup') ||
      title.includes('install')) {
    return Settings;
  }

  // Download
  if (title.includes('download') || title.includes('export') || title.includes('save')) {
    return Download;
  }

  // Upload
  if (title.includes('upload') || title.includes('import')) {
    return Upload;
  }

  // Image
  if (title.includes('image') || title.includes('photo') || title.includes('picture') ||
      title.includes('screenshot')) {
    return Image;
  }

  // Video
  if (title.includes('video') || title.includes('movie') || title.includes('youtube')) {
    return Video;
  }

  // Audio/Voice
  if (title.includes('audio') || title.includes('voice') || title.includes('speech') ||
      title.includes('music') || title.includes('sound')) {
    return Mic;
  }

  // Calculate
  if (title.includes('calculat') || title.includes('math') || title.includes('number') ||
      title.includes('fibonacci') || title.includes('prime')) {
    return Calculator;
  }

  // Email
  if (title.includes('email') || title.includes('mail') || title.includes('message')) {
    return Mail;
  }

  // Shopping
  if (title.includes('shop') || title.includes('buy') || title.includes('price') ||
      title.includes('product') || title.includes('keyboard')) {
    return ShoppingCart;
  }

  // Map/Location
  if (title.includes('map') || title.includes('location') || title.includes('geo')) {
    return Map;
  }

  // Quick/Fast
  if (title.includes('quick') || title.includes('fast') || title.includes('tip') ||
      title.includes('best')) {
    return Zap;
  }

  // Default - use hash to select from variety of icons
  // Use sessionId if available, otherwise use title for consistency
  const hashSource = props.sessionId || props.title || 'default';
  const index = hashString(hashSource) % defaultIcons.length;
  return defaultIcons[index];
});
</script>
