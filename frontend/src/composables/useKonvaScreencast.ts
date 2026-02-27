/**
 * Konva Screencast Composable
 *
 * Manages a Konva.Image node that displays CDP screencast frames.
 * Uses imperative Konva API for high-performance 15fps updates,
 * bypassing Vue's reactivity system for frame data to avoid
 * proxy wrapping and dependency tracking overhead.
 *
 * Frame pipeline: ArrayBuffer → Blob → createImageBitmap → Konva.Image → batchDraw
 */
import { ref, shallowRef, onBeforeUnmount } from 'vue'
import type Konva from 'konva'
import type { FrameDimensions, ScreencastStats } from '@/types/liveViewer'

export function useKonvaScreencast() {
  // ---------------------------------------------------------------------------
  // State (reactive — for template bindings)
  // ---------------------------------------------------------------------------

  /** Current frame dimensions (updates only when dimensions change) */
  const frameDimensions = ref<FrameDimensions>({ width: 0, height: 0 })

  /** Whether at least one frame has been rendered */
  const hasFrame = shallowRef(false)

  /** Stats for debug overlay */
  const stats = ref<ScreencastStats>({
    frameCount: 0,
    bytesReceived: 0,
    fps: 0,
    bytesPerSec: 0,
    lastFrameTime: 0,
  })

  // ---------------------------------------------------------------------------
  // Internal (non-reactive — performance critical)
  // ---------------------------------------------------------------------------

  /** Direct reference to the Konva.Image node (set once via bindImageNode) */
  let _imageNode: Konva.Image | null = null
  /** Direct reference to the Konva.Layer containing the image */
  let _layer: Konva.Layer | null = null
  /** Offscreen canvas used as Konva.Image source for zero-copy frame updates */
  let _offscreenCanvas: HTMLCanvasElement | null = null
  let _offscreenCtx: CanvasRenderingContext2D | null = null
  /** Reusable HTMLImageElement for decoding JPEG frames */
  let _decodeImg: HTMLImageElement | null = null
  /** Pending object URL that hasn't been consumed yet */
  let _pendingUrl: string | null = null
  /** Whether a frame decode is currently in flight (prevents pileup) */
  let _decoding = false
  /** Timestamp when the current decode started — safety valve for stuck decodes */
  let _lastDecodeStart = 0

  // Stats internals
  let _statsInterval: number | null = null
  let _lastStatsTime = 0
  let _lastStatsFrameCount = 0
  let _lastStatsBytesReceived = 0

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /**
   * Bind the Konva.Image node and its parent layer.
   * Called once when the KonvaLiveStage component mounts.
   */
  function bindImageNode(imageNode: Konva.Image, layer: Konva.Layer): void {
    _imageNode = imageNode
    _layer = layer
    _ensureOffscreenCanvas()
  }

  /**
   * Unbind — called on teardown to release references.
   */
  function unbindImageNode(): void {
    _imageNode = null
    _layer = null
  }

  /**
   * Process an incoming binary frame from the WebSocket.
   * This is the hot path — optimized for minimal allocations.
   */
  function pushFrame(data: ArrayBuffer): void {
    if (!_imageNode || !_layer) return

    // Track bytes
    stats.value.bytesReceived += data.byteLength

    // If a decode is already in-flight, drop this frame (back-pressure).
    // Safety valve: if _decoding has been true for >2s, force-release it.
    // A single frame decode should never take >2s — this means the decode
    // pipeline got stuck (e.g., Image.onload/onerror never fired).
    if (_decoding) {
      const elapsed = Date.now() - _lastDecodeStart
      if (elapsed > 2000) {
        console.warn(`[Screencast] Decode stuck for ${elapsed}ms — force-releasing mutex`)
        _decoding = false
      } else {
        return
      }
    }

    _decoding = true
    _lastDecodeStart = Date.now()
    _decodeFrame(data)
  }

  /**
   * Reset state (e.g., on reconnect).
   */
  function reset(): void {
    hasFrame.value = false
    frameDimensions.value = { width: 0, height: 0 }
    stats.value = {
      frameCount: 0,
      bytesReceived: 0,
      fps: 0,
      bytesPerSec: 0,
      lastFrameTime: 0,
    }
    _lastStatsTime = Date.now()
    _lastStatsFrameCount = 0
    _lastStatsBytesReceived = 0
  }

  /**
   * Force frame dimensions to known values after crash recovery.
   *
   * After a browser crash, the backend resets viewport to DEFAULT_VIEWPORT
   * (1280x900). The frontend must also reset its expected dimensions so
   * the auto-fit logic recalculates scale correctly when the first
   * post-recovery frame arrives. Without this, stale dimensions cause
   * the screencast to appear "zoomed in".
   */
  function forceDimensionReset(width: number, height: number): void {
    frameDimensions.value = { width, height }
  }

  /**
   * Start periodic stats calculation (call on WS open).
   */
  function startStats(): void {
    stopStats()
    _lastStatsTime = Date.now()
    _lastStatsFrameCount = 0
    _lastStatsBytesReceived = 0

    _statsInterval = window.setInterval(() => {
      const now = Date.now()
      const elapsed = (now - _lastStatsTime) / 1000
      if (elapsed > 0) {
        const frames = stats.value.frameCount - _lastStatsFrameCount
        const bytes = stats.value.bytesReceived - _lastStatsBytesReceived
        stats.value.fps = frames / elapsed
        stats.value.bytesPerSec = bytes / elapsed
        _lastStatsTime = now
        _lastStatsFrameCount = stats.value.frameCount
        _lastStatsBytesReceived = stats.value.bytesReceived
      }
    }, 1000)
  }

  /**
   * Stop stats tracking.
   */
  function stopStats(): void {
    if (_statsInterval !== null) {
      clearInterval(_statsInterval)
      _statsInterval = null
    }
  }

  // ---------------------------------------------------------------------------
  // Internal — frame decode pipeline
  // ---------------------------------------------------------------------------

  function _ensureOffscreenCanvas(): void {
    if (!_offscreenCanvas) {
      _offscreenCanvas = document.createElement('canvas')
      _offscreenCtx = _offscreenCanvas.getContext('2d', {
        alpha: false,
        desynchronized: true,
      })
    }
  }

  /**
   * Decode a JPEG frame and draw it to the offscreen canvas,
   * then tell Konva to redraw the layer.
   *
   * Uses createImageBitmap when available (async, off-main-thread decode).
   * Falls back to HTMLImageElement + object URL for older browsers.
   */
  function _decodeFrame(data: ArrayBuffer): void {
    const blob = new Blob([data], { type: 'image/jpeg' })

    if (typeof createImageBitmap === 'function') {
      // Fast path: async decode on a worker thread
      createImageBitmap(blob)
        .then((bitmap) => {
          _renderBitmap(bitmap, data.byteLength)
          bitmap.close()
        })
        .catch(() => {
          // Fallback to HTMLImageElement path
          try {
            _decodeWithImage(blob, data.byteLength)
          } catch {
            _decoding = false
          }
        })
    } else {
      _decodeWithImage(blob, data.byteLength)
    }
  }

  /**
   * Render an ImageBitmap to the offscreen canvas and update Konva.
   */
  function _renderBitmap(bitmap: ImageBitmap, _byteLength?: number): void {
    _ensureOffscreenCanvas()
    if (!_offscreenCanvas || !_offscreenCtx || !_imageNode || !_layer) {
      _decoding = false
      return
    }

    const w = bitmap.width
    const h = bitmap.height

    // Resize offscreen canvas only when dimensions change
    if (_offscreenCanvas.width !== w || _offscreenCanvas.height !== h) {
      _offscreenCanvas.width = w
      _offscreenCanvas.height = h
      // Re-acquire context after resize
      _offscreenCtx = _offscreenCanvas.getContext('2d', {
        alpha: false,
        desynchronized: true,
      })
      if (!_offscreenCtx) {
        _decoding = false
        return
      }
      // Update reactive dimensions
      frameDimensions.value = { width: w, height: h }
    }

    _offscreenCtx.drawImage(bitmap, 0, 0)

    // Point the Konva.Image at the offscreen canvas
    _imageNode.image(_offscreenCanvas)
    _imageNode.width(w)
    _imageNode.height(h)
    _layer.batchDraw()

    // Update stats
    hasFrame.value = true
    stats.value.frameCount++
    stats.value.lastFrameTime = Date.now()
    _decoding = false
  }

  /**
   * Fallback: decode via HTMLImageElement + object URL.
   */
  function _decodeWithImage(blob: Blob, _byteLength?: number): void {
    // Revoke any pending URL
    if (_pendingUrl) {
      URL.revokeObjectURL(_pendingUrl)
      _pendingUrl = null
    }

    const url = URL.createObjectURL(blob)
    _pendingUrl = url

    if (!_decodeImg) {
      _decodeImg = new Image()

      _decodeImg.onload = () => {
        if (!_decodeImg || !_offscreenCanvas || !_offscreenCtx || !_imageNode || !_layer) {
          _cleanup()
          return
        }

        const w = _decodeImg.naturalWidth
        const h = _decodeImg.naturalHeight

        if (_offscreenCanvas.width !== w || _offscreenCanvas.height !== h) {
          _offscreenCanvas.width = w
          _offscreenCanvas.height = h
          _offscreenCtx = _offscreenCanvas.getContext('2d', {
            alpha: false,
            desynchronized: true,
          })
          if (!_offscreenCtx) {
            _cleanup()
            return
          }
          frameDimensions.value = { width: w, height: h }
        }

        _offscreenCtx.drawImage(_decodeImg, 0, 0)

        _imageNode!.image(_offscreenCanvas)
        _imageNode!.width(w)
        _imageNode!.height(h)
        _layer!.batchDraw()

        hasFrame.value = true
        stats.value.frameCount++
        stats.value.lastFrameTime = Date.now()
        _cleanup()
      }

      _decodeImg.onerror = () => {
        _cleanup()
      }
    }

    _decodeImg.src = url
  }

  function _cleanup(): void {
    if (_pendingUrl) {
      URL.revokeObjectURL(_pendingUrl)
      _pendingUrl = null
    }
    _decoding = false
  }

  // ---------------------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------------------

  onBeforeUnmount(() => {
    stopStats()
    unbindImageNode()

    if (_pendingUrl) {
      URL.revokeObjectURL(_pendingUrl)
      _pendingUrl = null
    }

    _offscreenCanvas = null
    _offscreenCtx = null
    _decodeImg = null
  })

  // ---------------------------------------------------------------------------
  // Return
  // ---------------------------------------------------------------------------

  return {
    // Reactive state
    frameDimensions,
    hasFrame,
    stats,

    // Methods
    bindImageNode,
    unbindImageNode,
    pushFrame,
    reset,
    forceDimensionReset,
    startStats,
    stopStats,
  }
}
