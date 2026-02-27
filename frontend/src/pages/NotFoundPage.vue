<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

function goHome() {
  router.push('/chat')
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-gray-50">
    <div class="text-center">
      <h1 class="text-6xl font-bold text-gray-300">404</h1>
      <p class="mt-4 text-lg text-gray-600">Page not found</p>
      <p class="mt-2 text-sm text-gray-400">
        The page you're looking for doesn't exist or has been moved.
      </p>
      <button
        class="mt-6 rounded-lg bg-gray-900 px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-gray-800"
        @click="goHome"
      >
        Go to Chat
      </button>
    </div>
  </div>
</template>
