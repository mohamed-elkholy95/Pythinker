import { describe, expect, it } from 'vitest';

import { extractPlotlyFigureFromHtml, parsePlotlyFigureContract } from '@/utils/plotlyFigureContract';

describe('parsePlotlyFigureContract', () => {
  it('parses a direct data/layout payload', () => {
    const payload = {
      data: [{ type: 'bar', x: ['A'], y: [1] }],
      layout: { title: { text: 'Chart' } },
      config: { responsive: true },
    };

    const parsed = parsePlotlyFigureContract(payload);

    expect(parsed).not.toBeNull();
    expect(parsed?.data.length).toBe(1);
    expect(parsed?.layout.title).toEqual({ text: 'Chart' });
    expect(parsed?.config?.responsive).toBe(true);
  });

  it('parses a wrapped figure payload', () => {
    const payload = {
      figure: {
        data: [{ type: 'scatter', x: [1], y: [2] }],
        layout: { showlegend: true },
      },
    };

    const parsed = parsePlotlyFigureContract(payload);

    expect(parsed).not.toBeNull();
    expect(parsed?.layout.showlegend).toBe(true);
  });

  it('rejects invalid payload shape', () => {
    const parsed = parsePlotlyFigureContract({
      data: [{ type: 'bar' }, null],
      layout: {},
    });

    expect(parsed).toBeNull();
  });
});

describe('extractPlotlyFigureFromHtml', () => {
  it('extracts Plotly.newPlot payload from html', () => {
    const html = `
      <html>
        <body>
          <script>
            Plotly.newPlot("chart", [{"type":"bar","x":["A"],"y":[1]}], {"title":{"text":"Demo"}}, {"responsive":true});
          </script>
        </body>
      </html>
    `;

    const parsed = extractPlotlyFigureFromHtml(html);

    expect(parsed).not.toBeNull();
    expect(parsed?.data[0].type).toBe('bar');
    expect(parsed?.layout.title).toEqual({ text: 'Demo' });
    expect(parsed?.config?.responsive).toBe(true);
  });

  it('extracts plotly-data script payload when present', () => {
    const html = `
      <script id="plotly-data" type="application/json">
        {"data":[{"type":"line","x":[1,2],"y":[2,3]}],"layout":{"xaxis":{"title":"X"}}}
      </script>
    `;

    const parsed = extractPlotlyFigureFromHtml(html);

    expect(parsed).not.toBeNull();
    expect(parsed?.data[0].type).toBe('line');
    expect(parsed?.layout.xaxis).toEqual({ title: 'X' });
  });
});
