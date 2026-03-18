<template>
  <nav :class="['landing-nav', { 'nav-scrolled': isScrolled }]">
    <div class="nav-inner">
      <!-- Logo -->
      <a href="/" class="nav-logo" aria-label="Pythinker home">
        <img src="/pythinker_animated.svg" alt="" width="32" height="32" class="nav-logo-img" />
        <PythinkerLogoTextIcon />
      </a>

      <!-- Desktop links -->
      <div class="nav-links">
        <a v-for="link in navLinks" :key="link.href" :href="link.href" class="nav-link"
          @click.prevent="scrollTo(link.href)">{{ link.label }}</a>
      </div>

      <!-- Right actions -->
      <div class="nav-actions">
        <a href="https://github.com/mohamed-elkholy95/Pythinker" target="_blank" rel="noopener noreferrer"
          class="nav-icon-btn" aria-label="View on GitHub">
          <Github :size="18" />
        </a>
        <button class="nav-icon-btn" :aria-label="isDark ? 'Switch to light mode' : 'Switch to dark mode'"
          @click="toggleTheme">
          <Sun v-if="isDark" :size="18" />
          <Moon v-else :size="18" />
        </button>
        <a href="/login" class="nav-btn nav-btn--secondary">Log in</a>
        <a href="/login" class="nav-btn nav-btn--primary">Get Started</a>
      </div>

      <!-- Mobile hamburger -->
      <button class="nav-hamburger" :aria-expanded="mobileOpen" aria-label="Toggle navigation"
        @click="mobileOpen = !mobileOpen">
        <X v-if="mobileOpen" :size="22" />
        <Menu v-else :size="22" />
      </button>
    </div>

    <!-- Mobile menu -->
    <Transition name="slide-down">
      <div v-if="mobileOpen" class="nav-mobile">
        <a v-for="link in navLinks" :key="link.href" :href="link.href" class="nav-mobile-link"
          @click.prevent="scrollTo(link.href); mobileOpen = false">{{ link.label }}</a>
        <div class="nav-mobile-actions">
          <a href="https://github.com/mohamed-elkholy95/Pythinker" target="_blank" rel="noopener noreferrer"
            class="nav-btn nav-btn--secondary w-full text-center">
            <Github :size="16" /> GitHub
          </a>
          <a href="/login" class="nav-btn nav-btn--secondary w-full text-center">Log in</a>
          <a href="/login" class="nav-btn nav-btn--primary w-full text-center">Get Started</a>
        </div>
      </div>
    </Transition>
  </nav>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Sun, Moon, Menu, X, Github } from 'lucide-vue-next'
import PythinkerLogoTextIcon from '../icons/PythinkerLogoTextIcon.vue'
import { useThemeMode } from '../../composables/useThemeMode'

const { isDark, toggleTheme } = useThemeMode()
const isScrolled = ref(false)
const mobileOpen = ref(false)

const navLinks = [
  { label: 'Features', href: '#features' },
  { label: 'How It Works', href: '#how-it-works' },
  { label: 'Use Cases', href: '#use-cases' },
]

const scrollTo = (href: string) => {
  const id = href.replace('#', '')
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
}

const onScroll = () => { isScrolled.value = window.scrollY > 60 }

onMounted(() => window.addEventListener('scroll', onScroll, { passive: true }))
onUnmounted(() => window.removeEventListener('scroll', onScroll))
</script>

<style scoped>
.landing-nav {
  position: fixed; top: 0; left: 0; right: 0; z-index: 50;
  background: color-mix(in srgb, var(--background-main) 85%, transparent);
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid transparent;
  transition: border-color 0.3s ease, background 0.3s ease;
}
.nav-scrolled {
  border-bottom-color: var(--border-main);
  background: color-mix(in srgb, var(--background-main) 95%, transparent);
}
.nav-inner {
  max-width: 1200px; margin: 0 auto; padding: 0 24px; height: 64px;
  display: flex; align-items: center; justify-content: space-between;
}
.nav-logo { display: flex; align-items: center; gap: 10px; text-decoration: none; flex-shrink: 0; }
.nav-logo-img { width: 32px; height: 32px; }
.nav-links { display: flex; align-items: center; gap: 32px; }
.nav-link { font-size: 14px; font-weight: 500; color: var(--text-secondary); text-decoration: none; transition: color 0.2s; }
.nav-link:hover { color: var(--text-primary); }
.nav-actions { display: flex; align-items: center; gap: 12px; }
.nav-icon-btn {
  width: 36px; height: 36px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  background: transparent; border: none; color: var(--icon-secondary);
  cursor: pointer; text-decoration: none; transition: background 0.2s, color 0.2s;
}
.nav-icon-btn:hover { background: var(--fill-tsp-gray-main); color: var(--icon-primary); }
.nav-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  padding: 8px 18px; border-radius: 8px; font-size: 14px; font-weight: 500;
  text-decoration: none; cursor: pointer; transition: all 0.2s ease; border: none;
}
.nav-btn--secondary { color: var(--text-primary); background: transparent; }
.nav-btn--secondary:hover { background: var(--fill-tsp-gray-main); }
.nav-btn--primary { color: var(--text-onblack); background: var(--button-primary); }
.nav-btn--primary:hover { background: var(--button-primary-hover); }
.nav-hamburger {
  display: none; width: 40px; height: 40px; align-items: center; justify-content: center;
  background: transparent; border: none; color: var(--icon-primary); cursor: pointer; border-radius: 8px;
}
.nav-hamburger:hover { background: var(--fill-tsp-gray-main); }
.nav-mobile { display: none; flex-direction: column; padding: 16px 24px 24px; border-top: 1px solid var(--border-light); }
.nav-mobile-link {
  padding: 12px 0; font-size: 16px; font-weight: 500; color: var(--text-secondary);
  text-decoration: none; border-bottom: 1px solid var(--border-light);
}
.nav-mobile-link:hover { color: var(--text-primary); }
.nav-mobile-actions { display: flex; flex-direction: column; gap: 10px; margin-top: 16px; }
.slide-down-enter-active, .slide-down-leave-active { transition: all 0.25s ease; }
.slide-down-enter-from, .slide-down-leave-to { opacity: 0; transform: translateY(-8px); }
@media (max-width: 768px) {
  .nav-links, .nav-actions { display: none; }
  .nav-hamburger { display: flex; }
  .nav-mobile { display: flex; }
}
</style>
