<template>
  <div ref="monacoContainer" style="width: 100%; height: 100%"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, computed } from "vue";
import type { editor as MonacoEditorNamespace } from "monaco-editor/esm/vs/editor/editor.api";

type MonacoModule = typeof import("monaco-editor/esm/vs/editor/editor.api");

let monacoModule: MonacoModule | null = null;
let monacoLoadPromise: Promise<MonacoModule> | null = null;

const loadMonaco = async (): Promise<MonacoModule> => {
  if (monacoModule) {
    return monacoModule;
  }

  if (monacoLoadPromise) {
    return monacoLoadPromise;
  }

  monacoLoadPromise = (async () => {
    const [{ default: editorWorker }, { default: jsonWorker }] = await Promise.all([
      import("monaco-editor/esm/vs/editor/editor.worker?worker"),
      import("monaco-editor/esm/vs/language/json/json.worker?worker"),
    ]);

    const globalWithMonaco = self as typeof globalThis & {
      MonacoEnvironment?: {
        getWorker: (_: string, label: string) => Worker;
      };
    };

    if (!globalWithMonaco.MonacoEnvironment) {
      globalWithMonaco.MonacoEnvironment = {
        getWorker(_: string, label: string) {
          if (label === "json") {
            return new jsonWorker();
          }
          return new editorWorker();
        },
      };
    }

    const monaco = await import("monaco-editor/esm/vs/editor/editor.api");
    await Promise.all([
      import("monaco-editor/esm/vs/language/json/monaco.contribution"),
      import("monaco-editor/esm/vs/basic-languages/javascript/javascript.contribution"),
      import("monaco-editor/esm/vs/basic-languages/typescript/typescript.contribution"),
      import("monaco-editor/esm/vs/basic-languages/html/html.contribution"),
      import("monaco-editor/esm/vs/basic-languages/css/css.contribution"),
      import("monaco-editor/esm/vs/basic-languages/python/python.contribution"),
      import("monaco-editor/esm/vs/basic-languages/java/java.contribution"),
      import("monaco-editor/esm/vs/basic-languages/go/go.contribution"),
      import("monaco-editor/esm/vs/basic-languages/markdown/markdown.contribution"),
    ]);

    monacoModule = monaco;
    return monaco;
  })();

  return monacoLoadPromise;
};

interface MonacoEditorProps {
  value?: string;
  language?: string;
  filename?: string;
  readOnly?: boolean;
  theme?: string;
  lineNumbers?: 'on' | 'off' | 'relative' | 'interval';
  wordWrap?: 'on' | 'off' | 'wordWrapColumn' | 'bounded';
  minimap?: boolean;
  scrollBeyondLastLine?: boolean;
  automaticLayout?: boolean;
}

const props = withDefaults(defineProps<MonacoEditorProps>(), {
  value: "",
  language: "",
  filename: "",
  readOnly: true,
  theme: "vs",
  lineNumbers: "off",
  wordWrap: "on",
  minimap: false,
  scrollBeyondLastLine: false,
  automaticLayout: true,
});

const emit = defineEmits<{
  ready: [editor: MonacoEditorNamespace.IStandaloneCodeEditor];
  change: [value: string];
}>();

const monacoContainer = ref<HTMLElement | null>(null);
let editor: MonacoEditorNamespace.IStandaloneCodeEditor | null = null;

// Language mapping based on filename or explicit language
const languageFromFilename = (filename: string): string => {
  const extension = filename.split(".").pop()?.toLowerCase() || "";
  const languageMap: Record<string, string> = {
    js: "javascript",
    ts: "typescript",
    html: "html",
    css: "css",
    json: "json",
    py: "python",
    java: "java",
    c: "c",
    cpp: "cpp",
    go: "go",
    md: "markdown",
    txt: "plaintext",
    vue: "html",
    jsx: "javascript",
    tsx: "typescript",
  };
  return languageMap[extension] || "plaintext";
};

const computedLanguage = computed(() => {
  if (props.language) {
    return props.language;
  }
  if (props.filename) {
    return languageFromFilename(props.filename);
  }
  return "plaintext";
});

// Initialize Monaco editor
const initEditor = async () => {
  if (!monacoContainer.value || editor) {
    return;
  }

  const monaco = await loadMonaco();
  if (!monacoContainer.value || editor) {
    return;
  }

  editor = monaco.editor.create(monacoContainer.value, {
    value: props.value,
    language: computedLanguage.value,
    theme: props.theme,
    readOnly: props.readOnly,
    minimap: { enabled: props.minimap },
    scrollBeyondLastLine: props.scrollBeyondLastLine,
    automaticLayout: props.automaticLayout,
    lineNumbers: props.lineNumbers,
    wordWrap: props.wordWrap,
    scrollbar: {
      vertical: "auto",
      horizontal: "auto",
      verticalScrollbarSize: 8,
      horizontalScrollbarSize: 8,
      useShadows: false,
      verticalHasArrows: false,
      horizontalHasArrows: false,
      alwaysConsumeMouseWheel: false,
    },
    overviewRulerBorder: false,
    overviewRulerLanes: 0,
    hideCursorInOverviewRuler: true,
    renderLineHighlight: 'none',
    padding: { top: 12, bottom: 12 },
  });

  // Emit ready event
  emit("ready", editor);

  // Listen for content changes
  if (!props.readOnly) {
    editor.onDidChangeModelContent(() => {
      if (editor) {
        emit("change", editor.getValue());
      }
    });
  }
};

// Update editor content
const updateContent = (newValue: string) => {
  if (editor) {
    const model = editor.getModel();
    if (model) {
      model.setValue(newValue);
    } else {
      editor.setValue(newValue);
    }
  }
};

// Update editor language
const updateLanguage = (newLanguage: string) => {
  if (editor && monacoModule) {
    const model = editor.getModel();
    if (model) {
      monacoModule.editor.setModelLanguage(model, newLanguage);
    }
  }
};

// Expose methods to parent component
defineExpose({
  editor: () => editor,
  updateContent,
  updateLanguage,
  getValue: () => editor?.getValue() || "",
});

// Watch for value changes
watch(() => props.value, (newValue) => {
  if (newValue !== editor?.getValue()) {
    updateContent(newValue);
  }
});

// Watch for language changes
watch(computedLanguage, (newLanguage) => {
  updateLanguage(newLanguage);
});

onMounted(() => {
  void initEditor();
});

onBeforeUnmount(() => {
  if (editor) {
    try {
      editor.dispose();
    } catch {
      // Monaco Worker cleanup may throw during async teardown
    }
    editor = null;
  }
});
</script>

<style>
/* Monaco Editor Scrollbar Enhancement */
.monaco-editor .scrollbar {
  transition: opacity 0.2s ease;
}

.monaco-editor .scrollbar.fade {
  opacity: 0;
}

.monaco-editor:hover .scrollbar.fade {
  opacity: 1;
}

/* Vertical scrollbar */
.monaco-editor .scrollbar.vertical {
  width: 8px !important;
  right: 2px !important;
}

.monaco-editor .scrollbar.vertical .slider {
  width: 6px !important;
  left: 1px !important;
  border-radius: 6px !important;
  background: rgba(0, 0, 0, 0.12) !important;
  transition: background 0.15s ease, width 0.15s ease !important;
}

.monaco-editor .scrollbar.vertical:hover .slider,
.monaco-editor .scrollbar.vertical .slider:hover {
  width: 8px !important;
  left: 0 !important;
  background: rgba(0, 0, 0, 0.22) !important;
}

.monaco-editor .scrollbar.vertical .slider.active {
  background: rgba(0, 0, 0, 0.32) !important;
}

/* Horizontal scrollbar */
.monaco-editor .scrollbar.horizontal {
  height: 8px !important;
  bottom: 2px !important;
}

.monaco-editor .scrollbar.horizontal .slider {
  height: 6px !important;
  top: 1px !important;
  border-radius: 6px !important;
  background: rgba(0, 0, 0, 0.12) !important;
  transition: background 0.15s ease, height 0.15s ease !important;
}

.monaco-editor .scrollbar.horizontal:hover .slider,
.monaco-editor .scrollbar.horizontal .slider:hover {
  height: 8px !important;
  top: 0 !important;
  background: rgba(0, 0, 0, 0.22) !important;
}

.monaco-editor .scrollbar.horizontal .slider.active {
  background: rgba(0, 0, 0, 0.32) !important;
}

/* Dark theme adjustments */
.dark .monaco-editor .scrollbar.vertical .slider {
  background: rgba(255, 255, 255, 0.12) !important;
}

.dark .monaco-editor .scrollbar.vertical:hover .slider,
.dark .monaco-editor .scrollbar.vertical .slider:hover {
  background: rgba(255, 255, 255, 0.22) !important;
}

.dark .monaco-editor .scrollbar.vertical .slider.active {
  background: rgba(255, 255, 255, 0.35) !important;
}

.dark .monaco-editor .scrollbar.horizontal .slider {
  background: rgba(255, 255, 255, 0.12) !important;
}

.dark .monaco-editor .scrollbar.horizontal:hover .slider,
.dark .monaco-editor .scrollbar.horizontal .slider:hover {
  background: rgba(255, 255, 255, 0.22) !important;
}

.dark .monaco-editor .scrollbar.horizontal .slider.active {
  background: rgba(255, 255, 255, 0.35) !important;
}

/* Remove decorations overview ruler for cleaner look */
.monaco-editor .decorationsOverviewRuler {
  display: none !important;
}
</style> 
