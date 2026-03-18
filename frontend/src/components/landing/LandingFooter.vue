<template>
  <footer class="landing-footer">
    <div class="footer-inner">
      <div class="footer-grid">
        <div class="footer-brand">
          <a href="/" class="footer-logo" aria-label="Pythinker home">
            <img src="/logo.png" alt="" width="24" height="24" class="footer-logo-img" />
            <PythinkerLogoTextIcon />
          </a>
          <p class="footer-tagline">AI agents that run on your infrastructure.</p>
        </div>
        <div class="footer-links-group">
          <div v-for="group in linkGroups" :key="group.title" class="footer-col">
            <h4 class="footer-col-title">{{ group.title }}</h4>
            <ul class="footer-col-list">
              <li v-for="link in group.links" :key="link.label">
                <a v-if="link.href.startsWith('#')" :href="link.href" class="footer-link"
                  @click.prevent="scrollTo(link.href)">{{ link.label }}</a>
                <a v-else :href="link.href" class="footer-link"
                  :target="link.external ? '_blank' : undefined"
                  :rel="link.external ? 'noopener noreferrer' : undefined">{{ link.label }}</a>
              </li>
            </ul>
          </div>
        </div>
      </div>
      <div class="footer-bottom">
        <span class="footer-copy">&copy; {{ currentYear }} Pythinker. All rights reserved.</span>
      </div>
    </div>
  </footer>
</template>

<script setup lang="ts">
import PythinkerLogoTextIcon from '../icons/PythinkerLogoTextIcon.vue'

const currentYear = new Date().getFullYear()

const linkGroups = [
  { title: 'Product', links: [
    { label: 'Features', href: '#features' },
    { label: 'How It Works', href: '#how-it-works' },
    { label: 'Use Cases', href: '#use-cases' },
  ]},
  { title: 'Resources', links: [
    { label: 'Documentation', href: '/docs' },
    { label: 'GitHub', href: 'https://github.com', external: true },
  ]},
  { title: 'Legal', links: [
    { label: 'Privacy Policy', href: '/privacy' },
    { label: 'Terms of Service', href: '/terms' },
  ]},
]

const scrollTo = (href: string) => {
  document.getElementById(href.replace('#', ''))?.scrollIntoView({ behavior: 'smooth' })
}
</script>

<style scoped>
.landing-footer { background: var(--background-secondary); border-top: 1px solid var(--border-light); padding: 64px 24px 32px; }
.footer-inner { max-width: 1100px; margin: 0 auto; }
.footer-grid { display: flex; justify-content: space-between; gap: 48px; }
.footer-brand { max-width: 280px; }
.footer-logo { display: flex; align-items: center; gap: 8px; text-decoration: none; margin-bottom: 12px; }
.footer-logo-img { width: 24px; height: 24px; border-radius: 5px; }
.footer-tagline { font-size: 14px; line-height: 1.5; color: var(--text-tertiary); }
.footer-links-group { display: flex; gap: 56px; }
.footer-col-title {
  font-size: 13px; font-weight: 600; color: var(--text-primary);
  margin-bottom: 16px; text-transform: uppercase; letter-spacing: 0.04em;
}
.footer-col-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 10px; }
.footer-link { font-size: 14px; color: var(--text-tertiary); text-decoration: none; transition: color 0.2s; }
.footer-link:hover { color: var(--text-primary); }
.footer-bottom { margin-top: 48px; padding-top: 24px; border-top: 1px solid var(--border-light); }
.footer-copy { font-size: 13px; color: var(--text-tertiary); }
@media (max-width: 768px) {
  .landing-footer { padding: 48px 16px 24px; }
  .footer-grid { flex-direction: column; gap: 32px; }
  .footer-links-group { flex-wrap: wrap; gap: 32px; }
}
</style>
