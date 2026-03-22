import { ref, computed, type Ref } from 'vue'
import { getAllLibraryFiles, type LibraryFileItem } from '@/api/file'

export type FileCategory = 'all' | 'reports' | 'documents' | 'images' | 'code' | 'archives'
export type ViewMode = 'grid' | 'list'

const REPORT_PATTERN = /^report-.*\.md$/i

const CATEGORY_EXTENSIONS: Record<Exclude<FileCategory, 'all' | 'reports'>, Set<string>> = {
  documents: new Set(['md', 'txt', 'pdf', 'doc', 'docx', 'csv', 'xls', 'xlsx', 'rtf', 'odt', 'ods', 'ppt', 'pptx']),
  images: new Set(['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp', 'ico', 'tiff', 'heic']),
  code: new Set(['py', 'js', 'ts', 'jsx', 'tsx', 'vue', 'html', 'css', 'scss', 'json', 'yaml', 'yml', 'sh', 'bash', 'sql', 'java', 'go', 'rs', 'c', 'cpp', 'rb', 'php', 'swift', 'kt', 'toml', 'xml']),
  archives: new Set(['zip', 'tar', 'gz', '7z', 'rar', 'bz2', 'xz']),
}

const FAVORITES_KEY = 'pythinker-library-favorites'

function getExt(filename: string): string {
  const dot = filename.lastIndexOf('.')
  return dot > 0 ? filename.slice(dot + 1).toLowerCase() : ''
}

function isReport(file: LibraryFileItem): boolean {
  return file.metadata?.is_report === true || REPORT_PATTERN.test(file.filename)
}

function matchesCategory(file: LibraryFileItem, category: FileCategory): boolean {
  if (category === 'all') return true
  if (category === 'reports') return isReport(file)
  const ext = getExt(file.filename)
  return CATEGORY_EXTENSIONS[category]?.has(ext) ?? false
}

function loadFavorites(): Set<string> {
  try {
    const raw = localStorage.getItem(FAVORITES_KEY)
    return raw ? new Set(JSON.parse(raw) as string[]) : new Set()
  } catch {
    return new Set()
  }
}

function saveFavorites(favs: Set<string>): void {
  localStorage.setItem(FAVORITES_KEY, JSON.stringify([...favs]))
}

export interface SessionFileGroup {
  sessionId: string
  sessionTitle: string
  sessionLatestAt: number | null
  files: LibraryFileItem[]
}

export function useLibraryFiles() {
  const files: Ref<LibraryFileItem[]> = ref([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const searchQuery = ref('')
  const category: Ref<FileCategory> = ref('all')
  const viewMode: Ref<ViewMode> = ref('grid')
  const showFavoritesOnly = ref(false)
  const favorites = ref<Set<string>>(loadFavorites())

  async function fetchFiles() {
    isLoading.value = true
    error.value = null
    try {
      files.value = await getAllLibraryFiles()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load files'
    } finally {
      isLoading.value = false
    }
  }

  const filteredFiles = computed(() => {
    let result = files.value

    // Category filter
    if (category.value !== 'all') {
      result = result.filter((f) => matchesCategory(f, category.value))
    }

    // Favorites filter
    if (showFavoritesOnly.value) {
      result = result.filter((f) => favorites.value.has(f.file_id))
    }

    // Search
    if (searchQuery.value) {
      const q = searchQuery.value.toLowerCase()
      result = result.filter(
        (f) =>
          f.filename.toLowerCase().includes(q) ||
          f.session_title?.toLowerCase().includes(q) ||
          f.metadata?.title?.toLowerCase().includes(q),
      )
    }

    return result
  })

  const groupedBySession = computed((): SessionFileGroup[] => {
    const map = new Map<string, SessionFileGroup>()
    for (const file of filteredFiles.value) {
      const sid = file.session_id
      if (!map.has(sid)) {
        map.set(sid, {
          sessionId: sid,
          sessionTitle: file.session_title || 'Untitled Session',
          sessionLatestAt: file.session_latest_at,
          files: [],
        })
      }
      map.get(sid)!.files.push(file)
    }
    return [...map.values()]
  })

  function toggleFavorite(fileId: string) {
    const next = new Set(favorites.value)
    if (next.has(fileId)) {
      next.delete(fileId)
    } else {
      next.add(fileId)
    }
    favorites.value = next
    saveFavorites(next)
  }

  function isFavorite(fileId: string): boolean {
    return favorites.value.has(fileId)
  }

  const totalCount = computed(() => filteredFiles.value.length)

  return {
    files,
    isLoading,
    error,
    searchQuery,
    category,
    viewMode,
    showFavoritesOnly,
    favorites,
    filteredFiles,
    groupedBySession,
    totalCount,
    fetchFiles,
    toggleFavorite,
    isFavorite,
  }
}
