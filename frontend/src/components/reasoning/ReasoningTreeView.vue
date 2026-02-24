<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, withDefaults } from 'vue';
import {
  BarChart2, Check, CheckSquare, Chrome, Code, Cpu, Database, Eye, FileEdit,
  FileText, GitBranch, Globe, Layers3, Lightbulb, Minus, MousePointer, Pause, Play,
  Plus, Route, Search, Terminal, Wrench, Workflow, X, type LucideComponent,
  // canvas & message
  Brush, ImagePlus, Layers, LayoutTemplate, Maximize2, Trash2, Wand2,
  MessageCircle, MessageSquarePlus, BellRing,
} from 'lucide-vue-next';
import type { Message, PhaseContent, ReportContent, StepContent, ThoughtContent, ToolContent } from '@/types/message';
import type { ReasoningStage } from '@/components/ReasoningPipeline.vue';

type NodeKind = 'root' | 'phase' | 'step' | 'tool' | 'thought';
type NodeStatus =
  | 'pending'
  | 'started'
  | 'running'
  | 'completed'
  | 'failed'
  | 'blocked'
  | 'skipped'
  | 'calling'
  | 'called'
  | null;

interface TreeNode {
  id: string;
  kind: NodeKind;
  label: string;
  subtitle?: string;
  details?: string;
  timestamp?: number;
  status: NodeStatus;
  parentId: string | null;
  order: number;
  active: boolean;
  x: number;
  y: number;
  metadata: Record<string, unknown>;
}

interface TreeEdge {
  id: string;
  source: string;
  target: string;
  active: boolean;
}

interface GraphSnapshot {
  nodes: TreeNode[];
  edges: TreeEdge[];
  canvasWidth: number;
  canvasHeight: number;
}

interface Props {
  messages: Message[];
  activeReasoningState?: ReasoningStage;
  thinkingText?: string;
}

const props = withDefaults(defineProps<Props>(), {
  messages: () => [],
});

const ROOT_NODE_ID = 'reasoning-root';
const HORIZONTAL_GAP = 304;
const MARGIN_X = 100;
const MARGIN_Y = 72;

const runningStatuses = new Set<NodeStatus>(['started', 'running', 'calling']);

const makeRootNode = (): TreeNode => ({
  id: ROOT_NODE_ID,
  kind: 'root',
  label: 'Reasoning Session',
  subtitle: 'Live execution graph',
  details: 'Root node for this session.',
  status: null,
  parentId: null,
  order: 0,
  active: false,
  x: MARGIN_X,
  y: MARGIN_Y,
  metadata: {},
});

const graph = computed<GraphSnapshot>(() => {
  const nodes = new Map<string, TreeNode>();
  const parentMap = new Map<string, string | null>();
  const orderCounter = 1;
  let latestStepNodeId: string | null = null;
  let latestSemanticNodeId: string | null = null;
  let latestVerificationNodeId: string | null = null;

  const phaseNodeById = new Map<string, string>();
  const stepNodeById = new Map<string, string>();
  const seenToolCallIds = new Set<string>();
  const toolSignatureToNodeId = new Map<string, string>();

  const upsertNode = (partial: Omit<TreeNode, 'x' | 'y' | 'active'>) => {
    const existing = nodes.get(partial.id);
    if (existing) {
      existing.label = partial.label || existing.label;
      existing.subtitle = partial.subtitle || existing.subtitle;
      existing.details = partial.details || existing.details;
      existing.timestamp = partial.timestamp ?? existing.timestamp;
      existing.status = partial.status ?? existing.status;
      existing.metadata = { ...existing.metadata, ...partial.metadata };
      if (existing.parentId === ROOT_NODE_ID && partial.parentId && partial.parentId !== ROOT_NODE_ID) {
        existing.parentId = partial.parentId;
      }
      return existing;
    }

    const created: TreeNode = {
      ...partial,
      active: false,
      x: MARGIN_X,
      y: MARGIN_Y,
    };
    nodes.set(partial.id, created);
    return created;
  };

  const setParent = (nodeId: string, parentId: string | null) => {
    parentMap.set(nodeId, parentId ?? ROOT_NODE_ID);
    const node = nodes.get(nodeId);
    if (node) {
      node.parentId = parentId ?? ROOT_NODE_ID;
    }
  };

  const addThoughtNode = (
    stepNodeId: string | null,
    thought: ThoughtContent,
    fallbackId: string,
    orderSeed: number,
  ) => {
    const thoughtText = (
      thought.text
      || (thought as unknown as { content?: string }).content
      || ''
    ).trim();
    if (!thoughtText) return;

    const thoughtId = `thought:${thought.id || fallbackId}`;
    const parentId = stepNodeId || ROOT_NODE_ID;
    upsertNode({
      id: thoughtId,
      kind: 'thought',
      label: thoughtText.slice(0, 90),
      subtitle: thought.thought_type ? thought.thought_type.toUpperCase() : 'THOUGHT',
      details: thoughtText,
      timestamp: thought.timestamp,
      status: null,
      parentId,
      order: orderSeed,
      metadata: {
        thought_type: thought.thought_type,
        confidence: thought.confidence,
      },
    });
    setParent(thoughtId, parentId);
  };

  const addToolNode = (
    stepNodeId: string | null,
    tool: ToolContent,
    orderSeed: number,
  ) => {
    if (seenToolCallIds.has(tool.tool_call_id)) return;
    seenToolCallIds.add(tool.tool_call_id);

    const toolNodeId = `tool:${tool.tool_call_id}`;
    const parentId = stepNodeId || ROOT_NODE_ID;
    const toolFunction = (tool.function || tool.name || 'tool').toLowerCase().trim();
    const toolFunctionBucket = toolFunction.includes('message')
      ? 'message'
      : toolFunction.includes('file')
        ? 'file'
        : toolFunction.includes('chart')
          ? 'chart'
          : toolFunction;
    // Humanize raw function names that have no display label
    const humanizeToolName = (fn: string): string => {
      const map: Record<string, string> = {
        canvas: 'Canvas',
        canvas_create_project: 'Create Canvas',
        canvas_get_state: 'Read Canvas',
        canvas_add_element: 'Add Element',
        canvas_modify_element: 'Edit Element',
        canvas_delete_elements: 'Delete Element',
        canvas_generate_image: 'Generate Image',
        canvas_arrange_layer: 'Arrange Layer',
        canvas_export: 'Export Canvas',
        message: 'Send Message',
        message_notify_user: 'Notify User',
        message_ask_user: 'Ask User',
      };
      return map[fn] || fn.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    };
    const rawFn = tool.function || tool.name || toolFunction || '';
    const baseLabel = tool.display_command || (rawFn ? humanizeToolName(rawFn) : 'Tool');
    const signatureText = (
      tool.command_summary
      || tool.display_command
      || tool.command
      || tool.name
      || tool.function
      || ''
    )
      .trim()
      .toLowerCase()
      .replace(/\s+/g, ' ');
    const isNoisyTool = toolFunctionBucket === 'message'
      || toolFunctionBucket === 'file'
      || toolFunctionBucket === 'chart';
    const coarseSignature = isNoisyTool
      ? toolFunctionBucket
      : (signatureText || baseLabel.toLowerCase());
    const toolSignature = `${parentId}|${toolFunctionBucket}|${coarseSignature}`;

    const existingNodeId = toolSignatureToNodeId.get(toolSignature);
    const existingNode = existingNodeId ? nodes.get(existingNodeId) : undefined;
    if (existingNode) {
      const rawIds = existingNode.metadata.merged_tool_call_ids;
      const mergedToolCallIds = Array.isArray(rawIds)
        ? rawIds.filter((id): id is string => typeof id === 'string')
        : [];
      if (!mergedToolCallIds.includes(tool.tool_call_id)) {
        mergedToolCallIds.push(tool.tool_call_id);
      }
      const repeatCount = mergedToolCallIds.length > 0 ? mergedToolCallIds.length : 1;
      const baseNodeLabel =
        typeof existingNode.metadata.base_label === 'string'
          ? existingNode.metadata.base_label
          : existingNode.label;

      existingNode.label = repeatCount > 1 ? `${baseNodeLabel} ×${repeatCount}` : baseNodeLabel;
      const humanFn = tool.function ? humanizeToolName(tool.function) : existingNode.subtitle;
      existingNode.subtitle = repeatCount > 1
        ? `${humanFn} • ${repeatCount}×`
        : (humanFn || existingNode.subtitle);
      existingNode.timestamp = tool.timestamp ?? existingNode.timestamp;
      existingNode.status = tool.status ?? existingNode.status;
      existingNode.details = tool.command_summary || tool.command || tool.display_command || existingNode.details;
      existingNode.metadata = {
        ...existingNode.metadata,
        repeat_count: repeatCount,
        merged_tool_call_ids: mergedToolCallIds,
        last_tool_call_id: tool.tool_call_id,
        tool_signature: toolSignature,
        base_label: baseNodeLabel,
      };
      return;
    }

    upsertNode({
      id: toolNodeId,
      kind: 'tool',
      label: baseLabel,
      subtitle: rawFn ? humanizeToolName(rawFn) : undefined,
      details: tool.command_summary || tool.command || tool.display_command || tool.function || undefined,
      timestamp: tool.timestamp,
      status: tool.status,
      parentId,
      order: orderSeed,
      metadata: {
        tool_call_id: tool.tool_call_id,
        function: tool.function,
        args: tool.args,
        repeat_count: 1,
        merged_tool_call_ids: [tool.tool_call_id],
        tool_signature: toolSignature,
        base_label: baseLabel,
      },
    });
    setParent(toolNodeId, parentId);
    toolSignatureToNodeId.set(toolSignature, toolNodeId);
  };

  const addStepNode = (step: StepContent, messageOrder: number) => {
    const stepNodeId = `step:${step.id}`;
    stepNodeById.set(step.id, stepNodeId);
    latestStepNodeId = stepNodeId;
    latestSemanticNodeId = stepNodeId;

    const preferredParent =
      (step.phase_id && phaseNodeById.get(step.phase_id)) || ROOT_NODE_ID;

    upsertNode({
      id: stepNodeId,
      kind: 'step',
      label: step.description,
      subtitle: step.step_type || 'STEP',
      details: step.sub_stage_history?.length
        ? step.sub_stage_history.join(' -> ')
        : step.description,
      timestamp: step.timestamp,
      status: step.status,
      parentId: preferredParent,
      order: messageOrder,
      metadata: {
        step_id: step.id,
        step_type: step.step_type,
        phase_id: step.phase_id,
      },
    });
    setParent(stepNodeId, preferredParent);

    const verificationText = [
      step.description,
      step.step_type || '',
      ...(step.sub_stage_history || []),
    ]
      .join(' ')
      .toLowerCase();
    if (/(verif|validat|quality[_\s-]?check|finaliz)/.test(verificationText)) {
      latestVerificationNodeId = stepNodeId;
    }

    const stepTools = Array.isArray(step.tools) ? step.tools : [];
    stepTools.forEach((tool, toolIndex) => {
      addToolNode(stepNodeId, tool, messageOrder * 100 + toolIndex);
    });

    const stepItems = Array.isArray(step.items) ? step.items : [];
    stepItems
      ?.filter((item) => item.type === 'thought')
      .forEach((item, itemIndex) => {
        const thought = item.content as ThoughtContent;
        addThoughtNode(stepNodeId, thought, `${step.id}-${itemIndex}`, messageOrder * 1000 + itemIndex);
      });
  };

  nodes.set(ROOT_NODE_ID, makeRootNode());
  parentMap.set(ROOT_NODE_ID, null);

  const messageList = Array.isArray(props.messages) ? props.messages : [];
  messageList.forEach((message, messageIndex) => {
    const orderSeed = orderCounter + messageIndex;

    if (message.type === 'phase') {
      const phase = message.content as PhaseContent;
      const phaseNodeId = `phase:${phase.phase_id}`;
      phaseNodeById.set(phase.phase_id, phaseNodeId);
      latestSemanticNodeId = phaseNodeId;

      upsertNode({
        id: phaseNodeId,
        kind: 'phase',
        label: phase.label,
        subtitle: phase.phase_type.toUpperCase(),
        details: phase.skip_reason || phase.phase_type,
        timestamp: phase.timestamp,
        status: phase.status,
        parentId: ROOT_NODE_ID,
        order: orderSeed,
        metadata: {
          phase_id: phase.phase_id,
          phase_type: phase.phase_type,
          total_phases: phase.total_phases,
        },
      });
      setParent(phaseNodeId, ROOT_NODE_ID);

      const phaseText = `${phase.label} ${phase.phase_type}`.toLowerCase();
      if (/(verif|validat|quality[_\s-]?check|finaliz)/.test(phaseText)) {
        latestVerificationNodeId = phaseNodeId;
      }

      const phaseSteps = Array.isArray(phase.steps) ? phase.steps : [];
      phaseSteps.forEach((step, phaseStepIndex) => {
        addStepNode(step, orderSeed * 10 + phaseStepIndex);
      });

      return;
    }

    if (message.type === 'step') {
      addStepNode(message.content as StepContent, orderSeed);
      return;
    }

    if (message.type === 'tool') {
      addToolNode(latestStepNodeId, message.content as ToolContent, orderSeed);
      return;
    }

    if (message.type === 'thought') {
      const thought = message.content as unknown as ThoughtContent;
      addThoughtNode(latestStepNodeId, thought, message.id, orderSeed);
    }
  });

  const lastReportMessage = [...messageList].reverse().find((message) => message.type === 'report');
  const hasReport = Boolean(lastReportMessage);
  const hasTaskCompleted = props.activeReasoningState === 'completed' || hasReport;
  const completionBaseParentId = latestVerificationNodeId || latestSemanticNodeId || ROOT_NODE_ID;
  const terminalBaseOrder = orderCounter + messageList.length + 10_000;

  if (hasTaskCompleted || hasReport) {
    let combinedDetails = 'All execution stages finished successfully.';
    const combinedMetadata: Record<string, unknown> = {
      terminal: true,
      terminal_type: 'completion_and_report',
      task_completed: hasTaskCompleted,
      report_generated: hasReport,
    };

    if (lastReportMessage) {
      const reportContent = lastReportMessage.content as ReportContent;
      const reportTitle = (reportContent.title || '').trim() || 'Report generated';
      combinedDetails = reportContent.content?.trim()
        ? `All execution stages finished and final report generated: ${reportTitle}`
        : `All execution stages finished and final report generated: ${reportTitle}`;
      combinedMetadata.report_id = reportContent.id;
      combinedMetadata.report_title = reportTitle;
    }

    const terminalNodeId = 'terminal:completion-report';
    upsertNode({
      id: terminalNodeId,
      kind: 'step',
      label: hasReport ? 'Task completed • Report generated' : 'Task completed',
      subtitle: hasReport ? 'completion · output' : 'completion',
      details: combinedDetails,
      status: 'completed',
      parentId: completionBaseParentId,
      order: terminalBaseOrder,
      metadata: combinedMetadata,
    });
    setParent(terminalNodeId, completionBaseParentId);
  }

  const nodeList = [...nodes.values()].sort((a, b) => a.order - b.order);
  const nodeById = new Map(nodeList.map((node) => [node.id, node]));

  // Re-anchor non-semantic root children under the nearest semantic branch
  // to reduce root-level edge clutter in left->right flow.
  const rootChildren = nodeList
    .filter((node) => node.id !== ROOT_NODE_ID && (parentMap.get(node.id) ?? ROOT_NODE_ID) === ROOT_NODE_ID)
    .sort((a, b) => a.order - b.order);
  const semanticRoots = rootChildren.filter((node) => node.kind === 'phase' || node.kind === 'step');

  if (semanticRoots.length > 0) {
    let currentSemanticRootId = semanticRoots[0].id;
    for (const child of rootChildren) {
      if (child.kind === 'phase' || child.kind === 'step') {
        currentSemanticRootId = child.id;
        continue;
      }
      setParent(child.id, currentSemanticRootId);
    }

    // Force a single left->right backbone for top-level semantic nodes.
    for (let index = 1; index < semanticRoots.length; index += 1) {
      setParent(semanticRoots[index].id, semanticRoots[index - 1].id);
    }
  }

  const buildChildrenByParent = () => {
    const map = new Map<string, string[]>();
    for (const node of nodeList) {
      if (node.id === ROOT_NODE_ID) continue;
      const parentId = parentMap.get(node.id) ?? ROOT_NODE_ID;
      if (!map.has(parentId)) {
        map.set(parentId, []);
      }
      map.get(parentId)?.push(node.id);
    }
    for (const [, childIds] of map) {
      childIds.sort((a, b) => (nodeById.get(a)?.order ?? 0) - (nodeById.get(b)?.order ?? 0));
    }
    return map;
  };

  let childrenByParent = buildChildrenByParent();

  // Convert dense sibling tool/thought fans into compact chains to avoid spaghetti edges.
  for (const [, childIds] of childrenByParent) {
    const supportChildren = childIds.filter((childId) => {
      const kind = nodeById.get(childId)?.kind;
      return kind === 'tool' || kind === 'thought';
    });
    if (supportChildren.length <= 1) continue;

    for (let index = 1; index < supportChildren.length; index += 1) {
      setParent(supportChildren[index], supportChildren[index - 1]);
    }
  }

  childrenByParent = buildChildrenByParent();

  const depthByNode = new Map<string, number>();
  let maxDepth = 0;
  const assignDepth = (nodeId: string, depth: number) => {
    depthByNode.set(nodeId, depth);
    maxDepth = Math.max(maxDepth, depth);
    const parentNode = nodeById.get(nodeId);
    const children = childrenByParent.get(nodeId) || [];
    for (const childId of children) {
      const childNode = nodeById.get(childId);
      const sameSupportLane = (parentNode?.kind === 'tool' || parentNode?.kind === 'thought')
        && (childNode?.kind === 'tool' || childNode?.kind === 'thought');
      assignDepth(childId, depth + (sameSupportLane ? 0 : 1));
    }
  };
  assignDepth(ROOT_NODE_ID, 0);

  const rootChildrenAfterReanchor = (childrenByParent.get(ROOT_NODE_ID) ?? [])
    .filter((childId) => {
      const kind = nodeById.get(childId)?.kind;
      return kind === 'phase' || kind === 'step';
    });
  const branchRoots = rootChildrenAfterReanchor.length > 0
    ? rootChildrenAfterReanchor
    : (childrenByParent.get(ROOT_NODE_ID) ?? []);

  const distributeAround = (center: number, count: number, gap: number): number[] => {
    if (count <= 0) return [];
    if (count === 1) return [center];
    const start = center - ((count - 1) * gap) / 2;
    return Array.from({ length: count }, (_, index) => start + index * gap);
  };

  const idealYByNode = new Map<string, number>();
  const branchGap = branchRoots.length > 4 ? 188 : 220;
  const branchCenterY = MARGIN_Y + 220 + ((branchRoots.length - 1) * branchGap) / 2;

  const assignIdealY = (nodeId: string, preferredY: number) => {
    idealYByNode.set(nodeId, preferredY);
    const children = childrenByParent.get(nodeId) || [];
    if (children.length === 0) return;

    const semanticChildren = children.filter((childId) => {
      const kind = nodeById.get(childId)?.kind;
      return kind === 'phase' || kind === 'step';
    });
    const supportingChildren = children.filter((childId) => !semanticChildren.includes(childId));

    const semanticTargets = distributeAround(preferredY, semanticChildren.length, 158);
    semanticChildren.forEach((childId, index) => {
      assignIdealY(childId, semanticTargets[index]);
    });

    const supportingCenterY = semanticChildren.length > 0 ? preferredY + 78 : preferredY;
    const supportingTargets = distributeAround(supportingCenterY, supportingChildren.length, 88);
    supportingChildren.forEach((childId, index) => {
      assignIdealY(childId, supportingTargets[index]);
    });
  };

  idealYByNode.set(ROOT_NODE_ID, branchCenterY);
  const branchTargets = distributeAround(branchCenterY, branchRoots.length, branchGap);
  branchRoots.forEach((childId, index) => {
    assignIdealY(childId, branchTargets[index]);
  });

  let fallbackY = branchCenterY + Math.max(1, branchRoots.length) * branchGap;
  const fallbackGap = 112;
  for (const node of nodeList) {
    if (idealYByNode.has(node.id)) continue;
    idealYByNode.set(node.id, fallbackY);
    fallbackY += fallbackGap;
  }

  const finalYByNode = new Map<string, number>();
  const nodeIdsByDepth = new Map<number, string[]>();
  for (const node of nodeList) {
    const depth = depthByNode.get(node.id) ?? 0;
    if (!nodeIdsByDepth.has(depth)) {
      nodeIdsByDepth.set(depth, []);
    }
    nodeIdsByDepth.get(depth)?.push(node.id);
  }

  for (const [depth, depthNodeIds] of nodeIdsByDepth) {
    if (depth === 0) {
      finalYByNode.set(ROOT_NODE_ID, idealYByNode.get(ROOT_NODE_ID) ?? branchCenterY);
      continue;
    }
    const sorted = [...depthNodeIds].sort(
      (a, b) => (idealYByNode.get(a) ?? 0) - (idealYByNode.get(b) ?? 0),
    );
    let cursor = Number.NEGATIVE_INFINITY;
    for (const nodeId of sorted) {
      const node = nodeById.get(nodeId);
      if (!node) continue;
      const baseGap = node.kind === 'tool' || node.kind === 'thought' ? 82 : 112;
      const ideal = idealYByNode.get(nodeId) ?? 0;
      const nextY = Number.isFinite(cursor) ? Math.max(ideal, cursor + baseGap) : ideal;
      finalYByNode.set(nodeId, nextY);
      cursor = nextY;
    }
  }

  const allFinalY = [...finalYByNode.values()];
  const minFinalY = allFinalY.length > 0 ? Math.min(...allFinalY) : MARGIN_Y;
  const maxFinalY = allFinalY.length > 0 ? Math.max(...allFinalY) : MARGIN_Y + 420;
  const yOffset = MARGIN_Y + 60 - minFinalY;
  const rootCenterX = MARGIN_X + 140;
  const canvasWidth = Math.max(1200, rootCenterX + maxDepth * HORIZONTAL_GAP + MARGIN_X + 240);
  const canvasHeight = Math.max(760, maxFinalY + yOffset + MARGIN_Y + 120);

  for (const node of nodeList) {
    const depth = depthByNode.get(node.id) ?? 0;
    const y = finalYByNode.get(node.id) ?? (MARGIN_Y + 60);
    node.x = rootCenterX + depth * HORIZONTAL_GAP;
    node.y = y + yOffset;
  }

  const latestRunningNode = [...nodeList]
    .reverse()
    .find((node) => runningStatuses.has(node.status));

  let fallbackByStage: TreeNode | undefined;
  if (!latestRunningNode && props.activeReasoningState && props.activeReasoningState !== 'idle') {
    if (props.activeReasoningState === 'retrieval' || props.activeReasoningState === 'generation') {
      fallbackByStage = [...nodeList].reverse().find((node) => node.kind === 'tool');
    } else if (props.activeReasoningState === 'planning') {
      fallbackByStage = [...nodeList].reverse().find((node) => node.kind === 'step');
    } else {
      fallbackByStage = [...nodeList].reverse().find((node) => node.kind === 'phase' || node.kind === 'step');
    }
  }

  const activeNodeSeed = latestRunningNode || fallbackByStage;
  const activeNodeIds = new Set<string>();

  if (activeNodeSeed) {
    let cursor: string | null | undefined = activeNodeSeed.id;
    while (cursor) {
      activeNodeIds.add(cursor);
      cursor = parentMap.get(cursor) ?? null;
    }
  }

  for (const node of nodeList) {
    node.active = activeNodeIds.has(node.id) || runningStatuses.has(node.status);
  }

  const edges: TreeEdge[] = [];
  for (const node of nodeList) {
    if (node.id === ROOT_NODE_ID) continue;
    const parentId = parentMap.get(node.id) ?? ROOT_NODE_ID;
    if (!nodeById.has(parentId)) continue;
    edges.push({
      id: `${parentId}::${node.id}`,
      source: parentId,
      target: node.id,
      active: activeNodeIds.has(node.id) || activeNodeIds.has(parentId),
    });
  }

  return {
    nodes: nodeList,
    edges,
    canvasWidth,
    canvasHeight,
  };
});

const selectedNodeId = ref<string | null>(null);
const canvasViewportRef = ref<HTMLElement | null>(null);
const viewportWidth = ref(0);
const viewportHeight = ref(0);
const fitToScreen = ref(false);
const manualZoom = ref(1);
const isCanvasPanning = ref(false);
const suppressNodeClick = ref(false);

let panPointerId: number | null = null;
let panStartX = 0;
let panStartY = 0;
let panStartScrollLeft = 0;
let panStartScrollTop = 0;
let panMoved = false;

let viewportResizeObserver: ResizeObserver | null = null;

const updateViewportSize = () => {
  const el = canvasViewportRef.value;
  if (!el) return;
  viewportWidth.value = el.clientWidth;
  viewportHeight.value = el.clientHeight;
};

onMounted(() => {
  updateViewportSize();
  if (!canvasViewportRef.value) return;
  viewportResizeObserver = new ResizeObserver(() => {
    updateViewportSize();
  });
  viewportResizeObserver.observe(canvasViewportRef.value);
});

onBeforeUnmount(() => {
  viewportResizeObserver?.disconnect();
  viewportResizeObserver = null;
});

const fitScale = computed(() => {
  if (!viewportWidth.value || !viewportHeight.value) return 1;
  const padding = 44;
  const availableWidth = Math.max(viewportWidth.value - padding * 2, 160);
  const widthScale = availableWidth / graph.value.canvasWidth;
  // Fit to width only so horizontal graphs remain readable.
  return Math.min(widthScale, 1);
});

const activeScale = computed(() => {
  if (fitToScreen.value) return fitScale.value;
  return Math.max(0.45, Math.min(manualZoom.value, 1.8));
});

const zoomPercentLabel = computed(() => `${Math.round(activeScale.value * 100)}%`);

const canvasStageStyle = computed(() => {
  const scale = activeScale.value;
  const scaledWidth = graph.value.canvasWidth * scale;
  const scaledHeight = graph.value.canvasHeight * scale;
  const offsetX = fitToScreen.value ? Math.max((viewportWidth.value - scaledWidth) / 2, 12) : 12;
  const offsetY = fitToScreen.value ? Math.max((viewportHeight.value - scaledHeight) / 2, 12) : 12;

  return {
    width: `${graph.value.canvasWidth}px`,
    height: `${graph.value.canvasHeight}px`,
    transform: `translate(${offsetX}px, ${offsetY}px) scale(${scale})`,
  };
});

const setFitMode = () => {
  fitToScreen.value = true;
};

const setManualZoom = () => {
  fitToScreen.value = false;
  manualZoom.value = 1;
};

const zoomIn = () => {
  fitToScreen.value = false;
  manualZoom.value = Math.min(1.8, Number((manualZoom.value + 0.1).toFixed(2)));
};

const zoomOut = () => {
  fitToScreen.value = false;
  manualZoom.value = Math.max(0.45, Number((manualZoom.value - 0.1).toFixed(2)));
};

const endCanvasPan = (pointerId: number) => {
  if (!isCanvasPanning.value || panPointerId !== pointerId) return;
  const viewport = canvasViewportRef.value;
  if (viewport && viewport.hasPointerCapture(pointerId)) {
    viewport.releasePointerCapture(pointerId);
  }
  isCanvasPanning.value = false;
  panPointerId = null;
  if (panMoved) {
    suppressNodeClick.value = true;
    window.setTimeout(() => {
      suppressNodeClick.value = false;
    }, 0);
  }
};

const onCanvasPointerDown = (event: PointerEvent) => {
  if (event.button !== 0 || !canvasViewportRef.value) return;
  isCanvasPanning.value = true;
  panPointerId = event.pointerId;
  panStartX = event.clientX;
  panStartY = event.clientY;
  panStartScrollLeft = canvasViewportRef.value.scrollLeft;
  panStartScrollTop = canvasViewportRef.value.scrollTop;
  panMoved = false;
  canvasViewportRef.value.setPointerCapture(event.pointerId);
};

const onCanvasPointerMove = (event: PointerEvent) => {
  if (!isCanvasPanning.value || panPointerId !== event.pointerId || !canvasViewportRef.value) return;
  const deltaX = event.clientX - panStartX;
  const deltaY = event.clientY - panStartY;
  if (Math.abs(deltaX) > 2 || Math.abs(deltaY) > 2) {
    panMoved = true;
  }
  canvasViewportRef.value.scrollLeft = panStartScrollLeft - deltaX;
  canvasViewportRef.value.scrollTop = panStartScrollTop - deltaY;
};

const onCanvasPointerUp = (event: PointerEvent) => {
  endCanvasPan(event.pointerId);
};

const onCanvasPointerCancel = (event: PointerEvent) => {
  endCanvasPan(event.pointerId);
};

const scrollNodeIntoView = async (nodeId: string | null) => {
  if (!nodeId || !canvasViewportRef.value) return;
  await nextTick();
  const escapedNodeId = nodeId.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  const nodeElement = canvasViewportRef.value.querySelector(`[data-node-id="${escapedNodeId}"]`) as HTMLElement | null;
  if (!nodeElement) return;
  nodeElement.scrollIntoView({
    behavior: 'smooth',
    block: 'center',
    inline: 'center',
  });
};

watch(
  graph,
  (snapshot) => {
    if (snapshot.nodes.length === 0) {
      selectedNodeId.value = null;
      return;
    }
    if (selectedNodeId.value && snapshot.nodes.some((node) => node.id === selectedNodeId.value)) {
      return;
    }
    const preferred = snapshot.nodes.find((node) => node.active && node.kind !== 'root')
      || snapshot.nodes.find((node) => node.kind !== 'root');
    selectedNodeId.value = preferred?.id || null;
  },
  { immediate: true },
);

watch(
  selectedNodeId,
  (nodeId) => {
    if (!fitToScreen.value) return;
    void scrollNodeIntoView(nodeId);
  },
);

const nodeById = computed(() => new Map(graph.value.nodes.map((node) => [node.id, node])));
const selectedNode = computed(() => {
  if (!selectedNodeId.value) return null;
  return nodeById.value.get(selectedNodeId.value) || null;
});

const nonRootNodeCount = computed(() => graph.value.nodes.filter((node) => node.kind !== 'root').length);
const activeNodeCount = computed(() => graph.value.nodes.filter((node) => node.active).length);
const activeEdgeParticles = computed(() => {
  return graph.value.edges
    .filter((edge) => edge.active)
    .slice(0, 10)
    .map((edge, index) => ({
      id: `${edge.id}:particle:${index}`,
      edge,
      duration: `${2.1 + (index % 4) * 0.48}s`,
      begin: `${(index % 6) * 0.22}s`,
      radius: Number((1.55 + (index % 3) * 0.28).toFixed(2)),
      pulseDuration: `${1.15 + (index % 4) * 0.3}s`,
      opacityBegin: `${(index % 5) * 0.18}s`,
    }));
});

const statusLabel = (status: NodeStatus): string => {
  if (!status) return 'Idle';
  return status.replace('_', ' ').toUpperCase();
};

const getStatusIcon = (status: NodeStatus) => {
  if (status === 'running' || status === 'started' || status === 'calling') return Play;
  if (status === 'completed' || status === 'called') return Check;
  return Pause;
};

const statusClass = (status: NodeStatus) => {
  if (!status) return 'status-idle';
  if (status === 'running' || status === 'started' || status === 'calling') return 'status-running';
  if (status === 'completed' || status === 'called') return 'status-completed';
  if (status === 'failed' || status === 'blocked') return 'status-error';
  if (status === 'skipped') return 'status-skipped';
  return 'status-idle';
};

const getToolIcon = (fn: string): LucideComponent => {
  const name = fn.toLowerCase();

  // ── Canvas tool family (canvas.py) ─────────────────────────────────────
  if (name === 'canvas_generate_image' || name.includes('canvas_gen')) return Wand2;
  if (name === 'canvas_add_element') return ImagePlus;
  if (name === 'canvas_modify_element') return Brush;
  if (name === 'canvas_delete_elements') return Trash2;
  if (name === 'canvas_arrange_layer') return Layers;
  if (name === 'canvas_export') return Maximize2;
  if (name === 'canvas_get_state') return LayoutTemplate;
  if (name === 'canvas_create_project' || name === 'canvas') return LayoutTemplate;

  // ── Message tool family (message.py) ───────────────────────────────────
  if (name === 'message_ask_user') return MessageSquarePlus;
  if (name === 'message_notify_user') return BellRing;
  if (name === 'message' || name.includes('message')) return MessageCircle;

  // ── Shell / terminal ────────────────────────────────────────────────────
  if (name.includes('terminal') || name.includes('bash') || name.includes('exec') || name.includes('shell') || name.includes('run_command')) return Terminal;

  // ── Browser ─────────────────────────────────────────────────────────────
  if (name.includes('navigate') || name.includes('chrome') || name.includes('cdp') || name.includes('browser_agent')) return Chrome;
  if (name.includes('browser') || name.includes('web_page') || name.includes('url')) return Globe;

  // ── Search ──────────────────────────────────────────────────────────────
  if (name.includes('search') || name.includes('serper') || name.includes('tavily') || name.includes('brave') || name.includes('web_search')) return Search;

  // ── Vision / screen ─────────────────────────────────────────────────────
  if (name.includes('screenshot') || name.includes('vision') || name.includes('screencast') || name.includes('screen')) return Eye;

  // ── File I/O ─────────────────────────────────────────────────────────────
  if (name.includes('read') && (name.includes('file') || name.includes('doc') || name.includes('text'))) return FileText;
  if (name.includes('write') || name.includes('edit') || name.includes('create_file') || name.includes('save')) return FileEdit;

  // ── Data / code ──────────────────────────────────────────────────────────
  if (name.includes('chart') || name.includes('plot') || name.includes('graph') || name.includes('plotly')) return BarChart2;
  if (name.includes('code') || name.includes('python') || name.includes('script') || name.includes('eval')) return Code;
  if (name.includes('database') || name.includes('mongo') || name.includes('redis') || name.includes('query') || name.includes('sql')) return Database;
  if (name.includes('cpu') || name.includes('system') || name.includes('process') || name.includes('memory')) return Cpu;
  if (name.includes('mouse') || name.includes('click') || name.includes('input') || name.includes('type')) return MousePointer;
  if (name.includes('check') || name.includes('verify') || name.includes('validate') || name.includes('test')) return CheckSquare;
  return Wrench;
};

/**
 * Returns a hex color for the node's icon based on its kind + tool function.
 * Used to set --node-icon-color inline so a single CSS rule handles all cases.
 */
const getNodeIconColor = (node: TreeNode): string => {
  if (node.kind === 'root')    return '#94a3b8'; // slate
  if (node.kind === 'phase')   return '#3b82f6'; // blue
  if (node.kind === 'step')    return '#06b6d4'; // cyan
  if (node.kind === 'thought') return '#8b5cf6'; // violet

  // tool — pick by function name
  const fn = String(node.metadata.function || node.label || '').toLowerCase();

  // canvas family — indigo
  if (fn.includes('canvas'))                                                     return '#6366f1';

  // message family — emerald
  if (fn.includes('message'))                                                    return '#10b981';

  // shell / terminal — orange
  if (fn.includes('terminal') || fn.includes('bash') || fn.includes('shell')
    || fn.includes('exec')    || fn.includes('run_command'))                     return '#f97316';

  // browser / navigation — sky
  if (fn.includes('navigate') || fn.includes('browser') || fn.includes('chrome')
    || fn.includes('cdp')     || fn.includes('web_page') || fn.includes('url')) return '#0ea5e9';

  // search — amber
  if (fn.includes('search') || fn.includes('serper') || fn.includes('tavily')
    || fn.includes('brave')  || fn.includes('web_search'))                      return '#f59e0b';

  // vision / screenshot — pink
  if (fn.includes('screenshot') || fn.includes('vision')
    || fn.includes('screencast') || fn.includes('screen'))                      return '#ec4899';

  // file read — teal
  if (fn.includes('read') && (fn.includes('file') || fn.includes('doc')))      return '#14b8a6';

  // file write / edit — lime
  if (fn.includes('write') || fn.includes('edit')
    || fn.includes('create_file') || fn.includes('save'))                       return '#84cc16';

  // chart / plot — purple
  if (fn.includes('chart') || fn.includes('plot')
    || fn.includes('graph')  || fn.includes('plotly'))                          return '#a855f7';

  // code / script — rose
  if (fn.includes('code') || fn.includes('python')
    || fn.includes('script') || fn.includes('eval'))                            return '#f43f5e';

  // database — yellow
  if (fn.includes('database') || fn.includes('mongo')
    || fn.includes('redis')   || fn.includes('query') || fn.includes('sql'))   return '#eab308';

  // system / process — neutral blue-gray
  if (fn.includes('cpu') || fn.includes('system')
    || fn.includes('process') || fn.includes('memory'))                         return '#64748b';

  // verify / check — green
  if (fn.includes('check') || fn.includes('verify')
    || fn.includes('validate') || fn.includes('test'))                          return '#22c55e';

  // default tool — warm gray
  return '#a8a29e';
};

const getNodeIcon = (node: TreeNode): LucideComponent => {
  if (node.kind === 'tool') {
    // Use metadata.function first; fall back to node label (e.g. "message", "canvas")
    const fn = String(node.metadata.function || node.label || node.metadata.tool_call_id || '');
    return getToolIcon(fn);
  }
  switch (node.kind) {
    case 'phase':   return Layers3;
    case 'step':    return GitBranch;
    case 'thought': return Lightbulb;
    case 'root':
    default:        return Workflow;
  }
};

const getNodeHalfWidth = (node: TreeNode): number => {
  if (node.kind === 'root') return 124;
  if (node.kind === 'tool') return 77;
  if (node.kind === 'thought') return 84;
  if (node.kind === 'phase' || node.kind === 'step') return 95;
  return 100;
};

const edgePath = (edge: TreeEdge): string => {
  const source = nodeById.value.get(edge.source);
  const target = nodeById.value.get(edge.target);
  if (!source || !target) return '';
  const sourceX = source.x + getNodeHalfWidth(source);
  const sourceY = source.y;
  const targetX = target.x - getNodeHalfWidth(target);
  const targetY = target.y;
  if (Math.abs(sourceY - targetY) < 6) {
    return `M ${sourceX} ${sourceY} L ${targetX} ${targetY}`;
  }
  const direction = targetX >= sourceX ? 1 : -1;
  const controlOffset = Math.max(56, Math.abs(targetX - sourceX) * 0.45);
  const cp1X = sourceX + controlOffset * direction;
  const cp2X = targetX - controlOffset * direction;
  return `M ${sourceX} ${sourceY} C ${cp1X} ${sourceY}, ${cp2X} ${targetY}, ${targetX} ${targetY}`;
};

const handleNodeClick = (nodeId: string) => {
  if (suppressNodeClick.value) return;
  selectedNodeId.value = nodeId;
};
</script>

<template>
  <div class="reasoning-tree-root">
    <div class="reasoning-tree-header">
      <div class="reasoning-tree-header-metrics">
        <div class="metric-pill">
          <Route :size="14" />
          <span>{{ nonRootNodeCount }} nodes</span>
        </div>
        <div class="metric-pill">
          <GitBranch :size="14" />
          <span>{{ activeNodeCount }} active</span>
        </div>
      </div>
      <div v-if="thinkingText" class="thinking-snippet" :title="thinkingText">
        {{ thinkingText }}
      </div>
      <div class="reasoning-view-controls">
        <button
          type="button"
          class="reasoning-control-btn"
          :class="{ 'reasoning-control-btn-active': fitToScreen }"
          @click="setFitMode"
        >
          Fit
        </button>
        <button
          type="button"
          class="reasoning-control-btn"
          :class="{ 'reasoning-control-btn-active': !fitToScreen }"
          @click="setManualZoom"
        >
          {{ zoomPercentLabel }}
        </button>
        <button type="button" class="reasoning-control-btn" @click="zoomOut" aria-label="Zoom out">
          <Minus :size="12" />
        </button>
        <button type="button" class="reasoning-control-btn" @click="zoomIn" aria-label="Zoom in">
          <Plus :size="12" />
        </button>
      </div>
    </div>

    <div v-if="nonRootNodeCount === 0" class="reasoning-tree-empty">
      <div class="reasoning-tree-empty-title">No reasoning graph yet</div>
      <p class="reasoning-tree-empty-subtitle">
        Run a task in agent mode to populate the chain-of-thought tree.
      </p>
    </div>

    <div v-else class="reasoning-tree-body" :class="{ 'reasoning-tree-body-has-sidebar': !!selectedNode }">
      <div
        ref="canvasViewportRef"
        class="reasoning-tree-canvas-scroll"
        :class="{ 'reasoning-tree-canvas-panning': isCanvasPanning }"
        @pointerdown="onCanvasPointerDown"
        @pointermove="onCanvasPointerMove"
        @pointerup="onCanvasPointerUp"
        @pointercancel="onCanvasPointerCancel"
      >
        <div class="reasoning-tree-canvas-stage" :style="canvasStageStyle">
          <div
            class="reasoning-tree-canvas"
            :style="{ width: `${graph.canvasWidth}px`, height: `${graph.canvasHeight}px` }"
          >
          <svg class="reasoning-tree-edges" :width="graph.canvasWidth" :height="graph.canvasHeight">
            <path
              v-for="edge in graph.edges"
              :key="edge.id"
              :d="edgePath(edge)"
              class="reasoning-tree-edge"
              :class="{ 'reasoning-tree-edge-active': edge.active }"
            />
            <g class="reasoning-edge-particles">
              <circle
                v-for="particle in activeEdgeParticles"
                :key="particle.id"
                class="reasoning-edge-particle"
                :r="particle.radius"
              >
                <animateMotion
                  :dur="particle.duration"
                  :begin="particle.begin"
                  repeatCount="indefinite"
                  :path="edgePath(particle.edge)"
                />
                <animate
                  attributeName="r"
                  :dur="particle.pulseDuration"
                  repeatCount="indefinite"
                  :begin="particle.begin"
                  :values="`${particle.radius * 0.78};${particle.radius * 1.24};${particle.radius * 0.78}`"
                />
                <animate
                  attributeName="opacity"
                  :dur="particle.pulseDuration"
                  repeatCount="indefinite"
                  :begin="particle.opacityBegin"
                  values="0.18;0.72;0.18"
                />
              </circle>
            </g>
          </svg>

          <button
            v-for="node in graph.nodes"
            :key="node.id"
            class="reasoning-node"
            :class="[
              `reasoning-node-${node.kind}`,
              { 'reasoning-node-active': node.active, 'reasoning-node-selected': selectedNodeId === node.id },
            ]"
            :data-node-id="node.id"
            :style="{ left: `${node.x}px`, top: `${node.y}px`, '--node-icon-color': getNodeIconColor(node) }"
            @click="handleNodeClick(node.id)"
          >
            <div class="reasoning-node-icon">
              <component :is="getNodeIcon(node)" :size="14" />
            </div>
            <div class="reasoning-node-text">
              <div class="reasoning-node-label">{{ node.label }}</div>
              <div v-if="node.subtitle" class="reasoning-node-subtitle">{{ node.subtitle }}</div>
            </div>
            <span v-if="node.status" class="reasoning-node-status" :class="statusClass(node.status)">
              <component :is="getStatusIcon(node.status)" :size="10" :title="statusLabel(node.status)" />
            </span>
          </button>
          </div>
        </div>
      </div>

      <aside v-if="selectedNode" class="reasoning-tree-sidebar">
        <div class="reasoning-tree-sidebar-header">
          <div class="reasoning-tree-sidebar-title-wrap">
            <component :is="getNodeIcon(selectedNode)" :size="16" />
            <h3 class="reasoning-tree-sidebar-title">{{ selectedNode.label }}</h3>
          </div>
          <button class="reasoning-tree-sidebar-close" @click="selectedNodeId = null" aria-label="Close details">
            <X :size="14" />
          </button>
        </div>

        <div class="reasoning-tree-sidebar-content">
          <div class="sidebar-field">
            <div class="sidebar-label">Type</div>
            <div class="sidebar-value">{{ selectedNode.kind.toUpperCase() }}</div>
          </div>
          <div class="sidebar-field">
            <div class="sidebar-label">Status</div>
            <div class="sidebar-value">
              <span class="reasoning-node-status" :class="statusClass(selectedNode.status)">
                <component :is="getStatusIcon(selectedNode.status)" :size="10" :title="statusLabel(selectedNode.status)" />
              </span>
            </div>
          </div>
          <div v-if="selectedNode.details" class="sidebar-field">
            <div class="sidebar-label">Details</div>
            <div class="sidebar-value sidebar-multiline">{{ selectedNode.details }}</div>
          </div>
          <div v-if="Object.keys(selectedNode.metadata).length > 0" class="sidebar-field">
            <div class="sidebar-label">Metadata</div>
            <pre class="sidebar-json">{{ JSON.stringify(selectedNode.metadata, null, 2) }}</pre>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.reasoning-tree-root {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}

.reasoning-tree-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.reasoning-tree-header-metrics {
  display: flex;
  align-items: center;
  gap: 8px;
}

.metric-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border-main);
  border-radius: 10px;
  padding: 4px 10px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  background: var(--background-menu-white);
}

.thinking-snippet {
  max-width: 460px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-tertiary);
  font-size: 12px;
}

.reasoning-view-controls {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px;
  border: 1px solid var(--border-main);
  border-radius: 10px;
  background: var(--background-menu-white);
}

.reasoning-fit-label {
  display: inline-flex;
  align-items: center;
  height: 28px;
  border: 1px solid var(--border-main);
  border-radius: 10px;
  padding: 0 10px;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
  background: var(--background-menu-white);
}

.reasoning-control-btn {
  min-width: 30px;
  height: 28px;
  border: 1px solid transparent;
  border-radius: 7px;
  padding: 0 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  transition: all 0.15s ease;
}

.reasoning-control-btn:hover {
  color: var(--text-primary);
  background: var(--fill-tsp-white-main);
}

.reasoning-control-btn-active {
  color: var(--text-primary);
  border-color: var(--border-main);
  background: var(--background-white-main);
}

.reasoning-tree-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  min-height: 280px;
  border: 1px dashed var(--border-main);
  border-radius: 16px;
  background: var(--fill-tsp-white-main);
  text-align: center;
  padding: 24px;
}

.reasoning-tree-empty-title {
  color: var(--text-primary);
  font-size: 18px;
  font-weight: 600;
}

.reasoning-tree-empty-subtitle {
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 14px;
  max-width: 520px;
}

.reasoning-tree-body {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  min-height: 0;
  flex: 1;
}

.reasoning-tree-body-has-sidebar {
  grid-template-columns: minmax(0, 1fr) 320px;
}

.reasoning-tree-canvas-scroll {
  border: 1px solid var(--border-main);
  border-radius: 16px;
  background: var(--background-menu-white);
  overflow-y: auto;
  overflow-x: auto;
  min-height: 0;
  position: relative;
  cursor: grab;
}

.reasoning-tree-canvas-stage {
  position: relative;
  transform-origin: top left;
  will-change: transform;
}

.reasoning-tree-canvas-panning {
  cursor: grabbing;
  user-select: none;
}

.reasoning-tree-canvas {
  position: relative;
  background-color: var(--background-menu-white);
  background-image:
    linear-gradient(
      to right,
      color-mix(in srgb, var(--border-main) 45%, transparent) 1px,
      transparent 1px
    ),
    linear-gradient(
      to bottom,
      color-mix(in srgb, var(--border-main) 45%, transparent) 1px,
      transparent 1px
    );
  background-size: 28px 28px;
}

.reasoning-tree-edges {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.reasoning-tree-edge {
  fill: none;
  stroke: var(--border-main);
  stroke-width: 1.3;
  opacity: 0.44;
}

.reasoning-tree-edge-active {
  stroke: var(--status-running);
  stroke-width: 2.2;
  opacity: 1;
}

.reasoning-edge-particles {
  pointer-events: none;
}

.reasoning-edge-particle {
  fill: color-mix(in srgb, var(--status-running) 74%, white 26%);
  filter: drop-shadow(0 0 2px color-mix(in srgb, var(--status-running) 44%, transparent));
  opacity: 0.38;
}

.reasoning-node {
  position: absolute;
  transform: translate(-50%, -50%);
  width: 200px;
  min-height: 68px;
  border: 1px solid var(--border-main);
  border-radius: 14px;
  background: var(--background-white-main);
  padding: 10px 12px;
  display: flex;
  align-items: center;
  gap: 9px;
  text-align: left;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
}

.reasoning-node:hover {
  border-color: var(--border-dark);
  box-shadow: 0 8px 24px var(--shadow-S);
}

.reasoning-node-selected {
  border-color: var(--status-running);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--status-running) 45%, transparent);
}

.reasoning-node-active {
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--status-running) 40%, transparent), 0 12px 28px var(--shadow-S);
}

.reasoning-node-active .reasoning-node-icon {
  animation: node-working-pulse 1.6s ease-in-out infinite;
}

@keyframes node-working-pulse {
  0%, 100% {
    transform: scale(1);
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--status-running) 0%, transparent);
  }
  50% {
    transform: scale(1.08);
    box-shadow: 0 0 0 6px color-mix(in srgb, var(--status-running) 24%, transparent);
  }
}

.reasoning-node-root {
  width: 248px;
  min-height: 72px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 6px;
  background: var(--fill-tsp-white-main);
  border-style: dashed;
}

.reasoning-node-root .reasoning-node-text {
  align-items: center;
}

.reasoning-node-root .reasoning-node-label {
  text-align: center;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.reasoning-node-root .reasoning-node-subtitle {
  text-align: center;
}

.reasoning-node-phase {
  background: color-mix(in srgb, var(--status-running) 7%, var(--background-white-main));
}

.reasoning-node-step {
  width: 190px;
  background: var(--background-white-main);
}

.reasoning-node-tool {
  width: 154px;
  min-height: 62px;
  padding: 7px 8px;
  background: color-mix(in srgb, var(--status-warning) 8%, var(--background-white-main));
}

.reasoning-node-tool .reasoning-node-icon {
  width: 20px;
  height: 20px;
}

.reasoning-node-tool .reasoning-node-label {
  font-size: 12px;
  -webkit-line-clamp: 1;
}

.reasoning-node-thought {
  width: 168px;
  min-height: 64px;
  padding: 7px 8px;
  background: color-mix(in srgb, var(--status-running) 8%, var(--background-white-main));
}

.reasoning-node-icon {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  border: 1px solid var(--border-main);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--text-secondary);
  background: var(--background-menu-white);
  box-shadow: 0 1px 2px color-mix(in srgb, var(--border-main) 40%, transparent);
}

/* Single rule drives icon color for every node kind via --node-icon-color */
.reasoning-node .reasoning-node-icon {
  color: var(--node-icon-color, var(--text-secondary));
  border-color: color-mix(in srgb, var(--node-icon-color, var(--border-main)) 28%, var(--border-main));
  background: color-mix(in srgb, var(--node-icon-color, transparent) 9%, var(--background-menu-white));
}

.reasoning-node-text {
  min-width: 0;
  flex: 1;
}

.reasoning-node-label {
  font-size: 12px;
  line-height: 1.3;
  color: var(--text-primary);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.reasoning-node-subtitle {
  margin-top: 2px;
  font-size: 10px;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reasoning-node-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  font-size: 10px;
  line-height: 1;
  font-weight: 700;
  padding: 0;
  border: none;
  background: transparent;
  min-width: 0;
  min-height: 0;
}

.status-running {
  color: var(--status-running);
}

.status-completed {
  color: var(--status-completed);
}

.status-error {
  color: var(--status-error, #ef4444);
}

.status-skipped {
  color: var(--text-tertiary);
}

.status-idle {
  color: var(--text-tertiary);
}

.reasoning-tree-sidebar {
  border: 1px solid var(--border-main);
  border-radius: 16px;
  background: var(--background-menu-white);
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.reasoning-tree-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 14px 14px 10px;
  border-bottom: 1px solid var(--border-main);
}

.reasoning-tree-sidebar-title-wrap {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
  min-width: 0;
}

.reasoning-tree-sidebar-title {
  margin: 0;
  font-size: 14px;
  line-height: 1.35;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reasoning-tree-sidebar-close {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 1px solid var(--border-main);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
}

.reasoning-tree-sidebar-close:hover {
  background: var(--fill-tsp-white-main);
  color: var(--text-primary);
}

.reasoning-tree-sidebar-content {
  padding: 12px 14px 14px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sidebar-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sidebar-label {
  color: var(--text-tertiary);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.sidebar-value {
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.45;
}

.sidebar-multiline {
  white-space: pre-wrap;
}

.sidebar-json {
  border: 1px solid var(--border-main);
  border-radius: 10px;
  padding: 10px;
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-secondary);
  background: var(--fill-tsp-white-main);
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 1024px) {
  .reasoning-tree-body-has-sidebar {
    grid-template-columns: 1fr;
  }
}
</style>
