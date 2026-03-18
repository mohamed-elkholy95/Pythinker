<template>
  <div class="landing-page">
    <LandingNav />
    <main>
      <LandingHero />
      <LandingFeatures />
      <LandingHowItWorks />
      <LandingUseCases />
      <LandingCTA />
    </main>
    <LandingFooter />
  </div>
</template>

<script setup lang="ts">
import LandingNav from '../components/landing/LandingNav.vue'
import LandingHero from '../components/landing/LandingHero.vue'
import LandingFeatures from '../components/landing/LandingFeatures.vue'
import LandingHowItWorks from '../components/landing/LandingHowItWorks.vue'
import LandingUseCases from '../components/landing/LandingUseCases.vue'
import LandingCTA from '../components/landing/LandingCTA.vue'
import LandingFooter from '../components/landing/LandingFooter.vue'
</script>

<style scoped>
.landing-page {
  min-height: 100vh;
  background: var(--background-main);
  color: var(--text-primary);
  font-family: var(--font-sans);
  overflow-x: hidden;
}
</style>
