import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import CanvasStage from '@/components/canvas/editor/CanvasStage.vue'
import type { CanvasElement, EditorState } from '@/types/canvas'

const baseEditorState: EditorState = {
  activeTool: 'select',
  activePageIndex: 0,
  selectedElementIds: [],
  zoom: 1,
  panX: 0,
  panY: 0,
  showGrid: false,
  snapEnabled: true,
  isDirty: false,
}

const element: CanvasElement = {
  id: 'element-1',
  type: 'rectangle',
  name: 'Card',
  x: 48,
  y: 64,
  width: 240,
  height: 140,
  rotation: 0,
  scale_x: 1,
  scale_y: 1,
  opacity: 1,
  visible: true,
  locked: false,
  z_index: 1,
  corner_radius: 16,
}

const StageStub = defineComponent({
  name: 'VStage',
  props: {
    config: {
      type: Object,
      required: true,
    },
  },
  setup(_props, { expose }) {
    expose({
      getNode: () => ({
        getPointerPosition: () => ({ x: 0, y: 0 }),
        x: () => 0,
        y: () => 0,
      }),
    })
    return {}
  },
  template: '<div class="stage-stub"><slot /></div>',
})

const LayerStub = defineComponent({
  name: 'VLayer',
  props: {
    config: {
      type: Object,
      default: undefined,
    },
  },
  setup(_props, { expose }) {
    expose({
      getNode: () => ({
        batchDraw: vi.fn(),
        getChildren: () => [],
      }),
    })
    return {}
  },
  template: '<div class="layer-stub" :data-listening="String(config?.listening ?? \'unset\')"><slot /></div>',
})

const TransformerStub = defineComponent({
  name: 'VTransformer',
  props: {
    config: {
      type: Object,
      required: true,
    },
  },
  setup(_props, { expose }) {
    expose({
      getNode: () => ({
        nodes: vi.fn(),
        getLayer: () => ({ batchDraw: vi.fn() }),
      }),
    })
    return {}
  },
  template: '<div class="transformer-stub" />',
})

const ShapeStub = defineComponent({
  props: {
    config: {
      type: Object,
      default: undefined,
    },
  },
  template: '<div class="shape-stub" :data-stroke="config?.stroke || \'\'" />',
})

describe('CanvasStage performance guardrails', () => {
  it('keeps non-interactive layers out of the hit graph', () => {
    const wrapper = mount(CanvasStage, {
      props: {
        elements: [element],
        selectedElementIds: [],
        highlightedElementIds: [],
        editorState: baseEditorState,
        pageWidth: 1280,
        pageHeight: 720,
        pageBackground: '#ffffff',
      },
      global: {
        stubs: {
          'v-stage': StageStub,
          'v-layer': LayerStub,
          'v-transformer': TransformerStub,
          'v-rect': ShapeStub,
          'v-ellipse': ShapeStub,
          'v-text': ShapeStub,
          'v-image': ShapeStub,
          'v-line': ShapeStub,
        },
      },
    })

    const nonListeningLayers = wrapper
      .findAll('.layer-stub')
      .filter((layer) => layer.attributes('data-listening') === 'false')

    expect(nonListeningLayers.length).toBeGreaterThanOrEqual(2)
  })

  it('renders a transient highlight shape for changed agent elements', () => {
    const wrapper = mount(CanvasStage, {
      props: {
        elements: [element],
        selectedElementIds: [],
        highlightedElementIds: ['element-1'],
        editorState: baseEditorState,
        pageWidth: 1280,
        pageHeight: 720,
        pageBackground: '#ffffff',
      },
      global: {
        stubs: {
          'v-stage': StageStub,
          'v-layer': LayerStub,
          'v-transformer': TransformerStub,
          'v-rect': ShapeStub,
          'v-ellipse': ShapeStub,
          'v-text': ShapeStub,
          'v-image': ShapeStub,
          'v-line': ShapeStub,
        },
      },
    })

    const highlightedShape = wrapper
      .findAll('.shape-stub')
      .find((shape) => shape.attributes('data-stroke') === 'rgba(59, 130, 246, 0.72)')

    expect(highlightedShape).toBeDefined()
  })
})
