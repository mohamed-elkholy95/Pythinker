<script setup lang="ts">
import { computed } from 'vue'
import { getFileIconColor } from '@/utils/fileType'

const props = defineProps<{
  filename: string
  size?: number
}>()

const sz = computed(() => props.size ?? 40)
const color = computed(() => getFileIconColor(props.filename))
const ext = computed(() => props.filename.split('.').pop()?.toLowerCase() ?? '')

type ContentType =
  | 'lines'
  | 'spreadsheet'
  | 'presentation'
  | 'code'
  | 'json'
  | 'html'
  | 'image'
  | 'video'
  | 'audio'
  | 'archive'
  | 'pdf'
  | 'link'

const contentType = computed((): ContentType => {
  const e = ext.value
  if (e === 'pdf') return 'pdf'
  if (['csv', 'xls', 'xlsx', 'ods'].includes(e)) return 'spreadsheet'
  if (['ppt', 'pptx', 'odp'].includes(e)) return 'presentation'
  if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg', 'ico', 'tiff', 'tif', 'heic', 'heif'].includes(e))
    return 'image'
  if (['mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv', '3gp', 'ogv'].includes(e)) return 'video'
  if (['mp3', 'wav', 'flac', 'aac', 'ogg', 'wma', 'm4a', 'opus'].includes(e)) return 'audio'
  if (['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz', 'lzma'].includes(e)) return 'archive'
  if (['json', 'yaml', 'yml', 'toml', 'xml'].includes(e)) return 'json'
  if (['url', 'webloc', 'link'].includes(e)) return 'link'
  if (['html', 'htm'].includes(e)) return 'html'
  const codeExts = [
    'js', 'ts', 'jsx', 'tsx', 'vue',
    'py', 'java', 'c', 'cpp', 'h', 'hpp',
    'go', 'rs', 'php', 'rb', 'swift',
    'kt', 'scala', 'css', 'scss',
    'sh', 'bash', 'sql',
  ]
  if (codeExts.includes(e)) return 'code'
  return 'lines'
})
</script>

<template>
  <!--
    Google Drive-style rounded square icon.
    Viewport: 32 × 32 (1:1 ratio)
    Body: rounded rect with rx="6"
    Symbols centered in the square.
  -->
  <svg
    :width="sz"
    :height="sz"
    viewBox="0 0 32 32"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    class="flex-shrink-0"
  >
    <!-- Rounded square background -->
    <rect width="32" height="32" rx="6" :fill="color" />

    <!-- ── Content symbols (centered in 32×32) ── -->

    <!-- Text / Markdown / Docs → horizontal lines -->
    <template v-if="contentType === 'lines'">
      <rect x="7" y="9"  width="18" height="2.2" rx="1.1" fill="white" fill-opacity="0.9" />
      <rect x="7" y="14" width="18" height="2.2" rx="1.1" fill="white" fill-opacity="0.9" />
      <rect x="7" y="19" width="18" height="2.2" rx="1.1" fill="white" fill-opacity="0.9" />
      <rect x="7" y="24" width="12" height="2.2" rx="1.1" fill="white" fill-opacity="0.9" />
    </template>

    <!-- Spreadsheet → grid/table -->
    <template v-else-if="contentType === 'spreadsheet'">
      <rect x="6" y="7" width="20" height="18" rx="2" stroke="white" stroke-width="1.8" fill="none" fill-opacity="0.9" />
      <line x1="6" y1="13" x2="26" y2="13" stroke="white" stroke-width="1.5" stroke-opacity="0.9" />
      <line x1="6" y1="19" x2="26" y2="19" stroke="white" stroke-width="1.5" stroke-opacity="0.9" />
      <line x1="14" y1="7" x2="14" y2="25" stroke="white" stroke-width="1.5" stroke-opacity="0.9" />
    </template>

    <!-- Presentation → bar chart -->
    <template v-else-if="contentType === 'presentation'">
      <rect x="6"  y="18" width="5" height="8" rx="1" fill="white" fill-opacity="0.9" />
      <rect x="13" y="11" width="5" height="15" rx="1" fill="white" fill-opacity="0.9" />
      <rect x="20" y="14" width="5" height="12" rx="1" fill="white" fill-opacity="0.9" />
    </template>

    <!-- Code → </> -->
    <template v-else-if="contentType === 'code'">
      <text
        x="16" y="21"
        text-anchor="middle"
        font-size="11"
        font-weight="800"
        fill="white"
        font-family="'Courier New', Courier, monospace"
        fill-opacity="0.95"
      >&lt;/&gt;</text>
    </template>

    <!-- JSON / YAML / config → {} -->
    <template v-else-if="contentType === 'json'">
      <text
        x="16" y="22"
        text-anchor="middle"
        font-size="14"
        font-weight="800"
        fill="white"
        font-family="'Courier New', Courier, monospace"
        fill-opacity="0.95"
      >{ }</text>
    </template>

    <!-- HTML → <> angle brackets -->
    <template v-else-if="contentType === 'html'">
      <text
        x="16" y="21"
        text-anchor="middle"
        font-size="12"
        font-weight="800"
        fill="white"
        font-family="'Courier New', Courier, monospace"
        fill-opacity="0.95"
      >&lt;&gt;</text>
    </template>

    <!-- PDF → "PDF" label -->
    <template v-else-if="contentType === 'pdf'">
      <text
        x="16" y="20"
        text-anchor="middle"
        font-size="9"
        font-weight="800"
        fill="white"
        font-family="Arial, Helvetica, sans-serif"
        fill-opacity="0.95"
        letter-spacing="0.5"
      >PDF</text>
    </template>

    <!-- Image → mountain + sun -->
    <template v-else-if="contentType === 'image'">
      <circle cx="11" cy="12" r="2.5" fill="white" fill-opacity="0.9" />
      <path d="M4 26 L11 16 L17 22 L22 17 L28 26 Z" fill="white" fill-opacity="0.9" />
    </template>

    <!-- Video → play triangle -->
    <template v-else-if="contentType === 'video'">
      <polygon points="11,8 11,24 25,16" fill="white" fill-opacity="0.9" />
    </template>

    <!-- Audio → music note -->
    <template v-else-if="contentType === 'audio'">
      <circle cx="11" cy="23" r="3.5" fill="white" fill-opacity="0.9" />
      <rect x="14" y="8" width="2" height="15" rx="1" fill="white" fill-opacity="0.9" />
      <rect x="14" y="8" width="8" height="2.5" rx="1" fill="white" fill-opacity="0.9" />
    </template>

    <!-- Archive → zipper/stacked lines -->
    <template v-else-if="contentType === 'archive'">
      <rect x="9" y="8"    width="14" height="2.2" rx="1" fill="white" fill-opacity="0.5" />
      <rect x="9" y="12.5" width="14" height="2.2" rx="1" fill="white" fill-opacity="0.65" />
      <rect x="9" y="17"   width="14" height="2.2" rx="1" fill="white" fill-opacity="0.8" />
      <rect x="9" y="21.5" width="14" height="2.2" rx="1" fill="white" fill-opacity="0.95" />
    </template>

    <!-- Link → chain links -->
    <template v-else-if="contentType === 'link'">
      <path
        d="M8 18 Q8 13 13 13 H16"
        stroke="white" stroke-width="2.5" stroke-linecap="round" fill="none"
      />
      <path
        d="M16 19 Q16 24 21 24 H24"
        stroke="white" stroke-width="2.5" stroke-linecap="round" fill="none"
      />
      <line x1="14" y1="14" x2="18" y2="23" stroke="white" stroke-width="2" stroke-linecap="round" />
    </template>
  </svg>
</template>
