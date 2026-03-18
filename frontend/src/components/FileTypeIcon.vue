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
  const codeExts = [
    'js', 'ts', 'jsx', 'tsx', 'vue',
    'py', 'java', 'c', 'cpp', 'h', 'hpp',
    'go', 'rs', 'php', 'rb', 'swift',
    'kt', 'scala', 'html', 'css', 'scss',
    'sh', 'bash', 'sql',
  ]
  if (codeExts.includes(e)) return 'code'
  return 'lines'
})
</script>

<template>
  <!--
    Viewport: 30 × 36  (5:6 ratio — classic paper proportions)
    Body:     M4,0 H21 L30,9 V32 Q30,36 26,36 H4 Q0,36 0,32 V4 Q0,0 4,0 Z
    Dog-ear:  M21,0 L30,9 H21 Z  (darkened fold overlay)
  -->
  <svg
    :width="sz"
    :height="sz"
    viewBox="0 0 30 36"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    class="flex-shrink-0"
  >
    <!-- Document body -->
    <path
      d="M4 0 H21 L30 9 V32 Q30 36 26 36 H4 Q0 36 0 32 V4 Q0 0 4 0 Z"
      :fill="color"
    />
    <!-- Dog-ear fold — subtle darkening only -->
    <path d="M21 0 L30 9 H21 Z" fill="rgba(0,0,0,0.18)" />

    <!-- ── Content symbols ── -->

    <!-- Text / Markdown / Docs → horizontal lines -->
    <template v-if="contentType === 'lines'">
      <rect x="5" y="17"   width="15" height="2.2" rx="1.1" fill="white" fill-opacity="0.9" />
      <rect x="5" y="21.5" width="15" height="2.2" rx="1.1" fill="white" fill-opacity="0.9" />
      <rect x="5" y="26"   width="10" height="2.2" rx="1.1" fill="white" fill-opacity="0.9" />
    </template>

    <!-- Spreadsheet → bold X (Google Sheets style) -->
    <template v-else-if="contentType === 'spreadsheet'">
      <text
        x="14" y="30"
        text-anchor="middle"
        font-size="15"
        font-weight="900"
        fill="white"
        font-family="Arial Black, Arial, sans-serif"
        fill-opacity="0.95"
      >X</text>
    </template>

    <!-- Presentation → bar chart -->
    <template v-else-if="contentType === 'presentation'">
      <rect x="5"  y="24" width="5" height="8"  rx="1" fill="white" fill-opacity="0.9" />
      <rect x="12" y="19" width="5" height="13" rx="1" fill="white" fill-opacity="0.9" />
      <rect x="19" y="21" width="5" height="11" rx="1" fill="white" fill-opacity="0.9" />
    </template>

    <!-- Code → </> -->
    <template v-else-if="contentType === 'code'">
      <text
        x="14" y="30"
        text-anchor="middle"
        font-size="10"
        font-weight="800"
        fill="white"
        font-family="'Courier New', Courier, monospace"
        fill-opacity="0.95"
      >&lt;/&gt;</text>
    </template>

    <!-- JSON / YAML / config → {} -->
    <template v-else-if="contentType === 'json'">
      <text
        x="14" y="30"
        text-anchor="middle"
        font-size="12"
        font-weight="800"
        fill="white"
        font-family="'Courier New', Courier, monospace"
        fill-opacity="0.95"
      >{}</text>
    </template>

    <!-- PDF → "PDF" label -->
    <template v-else-if="contentType === 'pdf'">
      <text
        x="14" y="27"
        text-anchor="middle"
        font-size="8"
        font-weight="800"
        fill="white"
        font-family="Arial, Helvetica, sans-serif"
        fill-opacity="0.95"
        letter-spacing="0.5"
      >PDF</text>
    </template>

    <!-- Image → mountain + circle (landscape icon) -->
    <template v-else-if="contentType === 'image'">
      <path d="M3 31 L9 21 L15 27 L20 22 L27 31 Z" fill="white" fill-opacity="0.9" />
      <circle cx="8" cy="19" r="2.5" fill="white" fill-opacity="0.9" />
    </template>

    <!-- Video → play triangle -->
    <template v-else-if="contentType === 'video'">
      <polygon points="9,17 9,30 22,23.5" fill="white" fill-opacity="0.9" />
    </template>

    <!-- Audio → music note -->
    <template v-else-if="contentType === 'audio'">
      <path
        d="M10 27 Q10 22 15.5 19.5 L15.5 26 Q15.5 29 12.5 29 Q10 29 10 27 Z"
        fill="white" fill-opacity="0.9"
      />
      <rect x="15.5" y="17.5" width="2" height="8.5" rx="1" fill="white" fill-opacity="0.9" />
      <rect x="15.5" y="17.5" width="8"   height="2.2" rx="1" fill="white" fill-opacity="0.9" />
    </template>

    <!-- Archive → stacked lines (zip layers) -->
    <template v-else-if="contentType === 'archive'">
      <rect x="8" y="17"   width="14" height="2"   rx="1" fill="white" fill-opacity="0.5" />
      <rect x="8" y="20.5" width="14" height="2"   rx="1" fill="white" fill-opacity="0.65" />
      <rect x="8" y="24"   width="14" height="2"   rx="1" fill="white" fill-opacity="0.8" />
      <rect x="8" y="27.5" width="14" height="2"   rx="1" fill="white" fill-opacity="0.95" />
    </template>

    <!-- Link → chain links -->
    <template v-else-if="contentType === 'link'">
      <path
        d="M7 24 Q7 20 11 20 H14"
        stroke="white" stroke-width="2.5" stroke-linecap="round" fill="none"
      />
      <path
        d="M16 26 Q16 30 20 30 H23"
        stroke="white" stroke-width="2.5" stroke-linecap="round" fill="none"
      />
      <line x1="13" y1="21" x2="17" y2="29" stroke="white" stroke-width="2" stroke-linecap="round" />
    </template>
  </svg>
</template>
