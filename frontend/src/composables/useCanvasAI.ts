/**
 * Canvas AI integration composable.
 * Handles image generation, editing, and NL canvas edits.
 */
import { ref } from 'vue'
import * as canvasApi from '@/api/canvas'
import type { CanvasProject } from '@/types/canvas'

export function useCanvasAI() {
  const generating = ref(false)
  const error = ref<string | null>(null)

  async function generateImage(
    prompt: string,
    width = 1024,
    height = 1024,
  ): Promise<string[]> {
    generating.value = true
    error.value = null
    try {
      const result = await canvasApi.generateImage({ prompt, width, height })
      return result.urls
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Image generation failed'
      return []
    } finally {
      generating.value = false
    }
  }

  async function editImage(imageUrl: string, instruction: string): Promise<string[]> {
    generating.value = true
    error.value = null
    try {
      const result = await canvasApi.editImage({ image_url: imageUrl, instruction })
      return result.urls
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Image edit failed'
      return []
    } finally {
      generating.value = false
    }
  }

  async function removeBackground(imageUrl: string): Promise<string[]> {
    generating.value = true
    error.value = null
    try {
      const result = await canvasApi.removeBackground({ image_url: imageUrl })
      return result.urls
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Background removal failed'
      return []
    } finally {
      generating.value = false
    }
  }

  async function applyAIEdit(
    projectId: string,
    instruction: string,
  ): Promise<CanvasProject | null> {
    generating.value = true
    error.value = null
    try {
      return await canvasApi.aiEdit(projectId, { instruction })
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'AI edit failed'
      return null
    } finally {
      generating.value = false
    }
  }

  return { generating, error, generateImage, editImage, removeBackground, applyAIEdit }
}
