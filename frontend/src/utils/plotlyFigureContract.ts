export interface PlotlyFigureContract {
  data: Array<Record<string, unknown>>;
  layout: Record<string, unknown>;
  config?: Record<string, unknown>;
}

const isRecord = (value: unknown): value is Record<string, unknown> => {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
};

const isTraceArray = (value: unknown): value is Array<Record<string, unknown>> => {
  if (!Array.isArray(value)) return false;
  return value.every((entry) => isRecord(entry));
};

const parseJson = (value: string): unknown | null => {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
};

const normalizeContractPayload = (payload: unknown): Record<string, unknown> | null => {
  if (!isRecord(payload)) return null;
  if (isTraceArray(payload.data)) return payload;

  const figure = payload.figure;
  if (isRecord(figure) && isTraceArray(figure.data)) {
    return figure;
  }

  return null;
};

export const parsePlotlyFigureContract = (payload: unknown): PlotlyFigureContract | null => {
  const normalized = normalizeContractPayload(payload);
  if (!normalized || !isTraceArray(normalized.data)) return null;

  const layoutCandidate = normalized.layout;
  if (layoutCandidate !== undefined && !isRecord(layoutCandidate)) return null;

  const configCandidate = normalized.config;
  if (configCandidate !== undefined && !isRecord(configCandidate)) return null;

  return {
    data: normalized.data,
    layout: isRecord(layoutCandidate) ? layoutCandidate : {},
    config: isRecord(configCandidate) ? configCandidate : undefined,
  };
};

export const extractPlotlyFigureFromHtml = (html: string): PlotlyFigureContract | null => {
  if (!html) return null;

  // Pattern 1: explicit JSON script tag
  const scriptTagMatch = html.match(/<script id="plotly-data" type="application\/json">([\s\S]*?)<\/script>/);
  if (scriptTagMatch) {
    const scriptPayload = parseJson(scriptTagMatch[1]);
    const parsedScriptPayload = parsePlotlyFigureContract(scriptPayload);
    if (parsedScriptPayload) return parsedScriptPayload;
  }

  // Pattern 2: Plotly.newPlot(..., data, layout, config)
  const withConfigMatch = html.match(
    /Plotly\.newPlot\([^,]+,\s*(\[[\s\S]*?\])\s*,\s*({[\s\S]*?})\s*,\s*({[\s\S]*?})\s*\)/
  );
  if (withConfigMatch) {
    const data = parseJson(withConfigMatch[1]);
    const layout = parseJson(withConfigMatch[2]);
    const config = parseJson(withConfigMatch[3]);
    const parsed = parsePlotlyFigureContract({ data, layout, config });
    if (parsed) return parsed;
  }

  // Pattern 3: Plotly.newPlot(..., data, layout)
  const basicMatch = html.match(/Plotly\.newPlot\([^,]+,\s*(\[[\s\S]*?\])\s*,\s*({[\s\S]*?})\s*\)/);
  if (basicMatch) {
    const data = parseJson(basicMatch[1]);
    const layout = parseJson(basicMatch[2]);
    const parsed = parsePlotlyFigureContract({ data, layout });
    if (parsed) return parsed;
  }

  return null;
};
