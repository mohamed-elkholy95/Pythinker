import { computed, Ref } from 'vue';
import type { ToolContent } from '../types/message';
import { useI18n } from 'vue-i18n';
import { getToolDisplay, extractToolUrl, getFaviconUrl } from '@/utils/toolDisplay';

export interface ToolInfo {
  icon: any;
  name: string;
  /** Full human-readable description (Manus-style) */
  description: string;
  /** @deprecated Use description instead */
  function: string;
  /** @deprecated Use description instead */
  functionArg: string;
  /** URL being targeted by this tool, if any */
  url: string | null;
  /** Favicon URL for the tool's target domain */
  faviconUrl: string | null;
}

export function useToolInfo(tool?: Ref<ToolContent | undefined>) {
  const { t } = useI18n();

  const toolInfo = computed<ToolInfo | null>(() => {
    if (!tool || !tool.value) return null;

    const toolValue = tool.value;
    const display = getToolDisplay({
      name: toolValue.name,
      function: toolValue.function,
      args: toolValue.args,
      display_command: toolValue.display_command
    });

    const toolUrl = extractToolUrl(toolValue.args);

    return {
      icon: display.icon || null,
      name: t(display.displayName),
      description: display.description,
      // Legacy fields for backward compatibility
      function: t(display.actionLabel),
      functionArg: display.resourceLabel,
      url: toolUrl,
      faviconUrl: toolUrl ? getFaviconUrl(toolUrl) : null,
    };
  });

  return {
    toolInfo
  };
}
