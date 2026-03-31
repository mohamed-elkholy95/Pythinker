import { ref } from 'vue';

/**
 * True while {@link TakeOverView} is showing full-screen VNC takeover.
 * Persistent CDP {@link LiveViewer} streams should pause to avoid duplicate
 * browser views, extra WebSocket load, and confusing stacked UIs.
 */
export const isTakeoverOverlayActive = ref(false);
