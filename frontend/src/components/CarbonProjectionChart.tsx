import React, { useMemo } from 'react';
import { useTranslation } from '@nekazari/sdk';
import type { ProjectionData } from '../api/carbonApi';

interface CarbonProjectionChartProps {
  data: ProjectionData;
}

const CHART_WIDTH = 400;
const CHART_HEIGHT = 240;
const PADDING = { top: 20, right: 20, bottom: 40, left: 55 };
const PLOT_WIDTH = CHART_WIDTH - PADDING.left - PADDING.right;
const PLOT_HEIGHT = CHART_HEIGHT - PADDING.top - PADDING.bottom;

const COLORS = {
  baseline: '#6B7280',
  project: '#059669',
  grid: '#E5E7EB',
  axis: '#9CA3AF',
  annotation: '#374151',
  annotationBg: '#F0FDF4',
};

const CarbonProjectionChart: React.FC<CarbonProjectionChartProps> = ({ data }) => {
  const { t } = useTranslation('carbon');

  const { points, yMax, yMin, pathBaseline, pathProject } = useMemo(() => {
    const years = data.projection_years;
    const baseline = data.baseline_soc;
    const project = data.project_soc;

    if (!baseline.length || !project.length) {
      return { points: [], yMax: 0, yMin: 0, pathBaseline: '', pathProject: '' };
    }

    const all = [...baseline, ...project];
    const yMaxVal = Math.max(...all) * 1.1;
    const yMinVal = Math.min(...all) * 0.9;
    const range = yMaxVal - yMinVal || 1;

    const scaleX = (i: number) => PADDING.left + (i / (years - 1 || 1)) * PLOT_WIDTH;
    const scaleY = (v: number) => PADDING.top + (1 - (v - yMinVal) / range) * PLOT_HEIGHT;

    const pts = Array.from({ length: years }, (_, i) => ({
      x: scaleX(i),
      y0: scaleY(baseline[i] ?? 0),
      y1: scaleY(project[i] ?? 0),
      label: `${i}`,
    }));

    const buildPath = (arr: number[]) =>
      arr
        .map((v, i) => {
          const x = scaleX(i);
          const y = scaleY(v);
          return i === 0 ? `M${x},${y}` : `L${x},${y}`;
        })
        .join('');

    return {
      points: pts,
      yMax: yMaxVal,
      yMin: yMinVal,
      pathBaseline: buildPath(baseline),
      pathProject: buildPath(project),
    };
  }, [data]);

  const finalDelta = data.annual_delta_tC_ha_yr.length > 0
    ? data.annual_delta_tC_ha_yr[data.annual_delta_tC_ha_yr.length - 1]
    : 0;

  const { years } = data;

  if (!data.baseline_soc.length || !data.project_soc.length) {
    return (
      <div
        style={{
          textAlign: 'center',
          padding: '40px 20px',
          color: '#9CA3AF',
          fontSize: '14px',
        }}
      >
        {t('no_data')}
      </div>
    );
  }

  const yTickCount = 5;
  const yRange = yMax - yMin;
  const yTicks = Array.from({ length: yTickCount }, (_, i) => {
    const val = yMin + (yRange * i) / (yTickCount - 1);
    return { val, label: val.toFixed(1) };
  });

  const xTickCount = Math.min(years, 6);
  const xTicks = Array.from({ length: xTickCount }, (_, i) => {
    const idx = Math.round((i * (years - 1)) / (xTickCount - 1));
    return { idx, label: `${idx}` };
  });

  return (
    <div style={{ maxWidth: '100%', overflowX: 'auto' }}>
      <svg
        width={CHART_WIDTH}
        height={CHART_HEIGHT}
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        style={{ display: 'block' }}
        role="img"
        aria-label={t('projection')}
      >
        {/* Grid lines */}
        {yTicks.map((tick, i) => {
          const y = PADDING.top + (1 - (tick.val - yMin) / yRange) * PLOT_HEIGHT;
          return (
            <g key={`grid-${i}`}>
              <line
                x1={PADDING.left}
                y1={y}
                x2={CHART_WIDTH - PADDING.right}
                y2={y}
                stroke={COLORS.grid}
                strokeWidth={1}
              />
              <text
                x={PADDING.left - 8}
                y={y + 4}
                textAnchor="end"
                fill={COLORS.axis}
                fontSize={11}
              >
                {tick.label}
              </text>
            </g>
          );
        })}

        {/* X-axis labels */}
        {xTicks.map((tick) => {
          const x = PADDING.left + (tick.idx / (years - 1 || 1)) * PLOT_WIDTH;
          return (
            <text
              key={`xtick-${tick.idx}`}
              x={x}
              y={CHART_HEIGHT - 8}
              textAnchor="middle"
              fill={COLORS.axis}
              fontSize={11}
            >
              {tick.label}
            </text>
          );
        })}

        {/* X-axis title */}
        <text
          x={CHART_WIDTH / 2}
          y={CHART_HEIGHT - 1}
          textAnchor="middle"
          fill={COLORS.axis}
          fontSize={11}
        >
          {t('units.tC_ha')}
        </text>

        {/* Baseline line */}
        <path d={pathBaseline} fill="none" stroke={COLORS.baseline} strokeWidth={2} strokeDasharray="6,3" />
        {/* Project line */}
        <path d={pathProject} fill="none" stroke={COLORS.project} strokeWidth={2.5} />

        {/* Legend */}
        <g transform={`translate(${CHART_WIDTH - PADDING.right - 100}, ${PADDING.top + 4})`}>
          <line x1={0} y1={0} x2={16} y2={0} stroke={COLORS.project} strokeWidth={2.5} />
          <text x={20} y={4} fontSize={11} fill={COLORS.project}>
            {t('project')}
          </text>
          <line x1={0} y1={16} x2={16} y2={16} stroke={COLORS.baseline} strokeWidth={2} strokeDasharray="6,3" />
          <text x={20} y={20} fontSize={11} fill={COLORS.baseline}>
            {t('baseline')}
          </text>
        </g>
      </svg>

      {/* Delta annotation */}
      {finalDelta !== 0 && (
        <div
          style={{
            marginTop: '8px',
            padding: '8px 12px',
            backgroundColor: COLORS.annotationBg,
            borderRadius: '6px',
            fontSize: '13px',
            color: COLORS.annotation,
            textAlign: 'center',
          }}
        >
          {t('soilCarbonDelta')}:{' '}
          <strong style={{ color: finalDelta > 0 ? '#059669' : '#DC2626' }}>
            {finalDelta > 0 ? '+' : ''}
            {finalDelta.toFixed(2)} {t('units.tC_ha_yr')}
          </strong>
        </div>
      )}
    </div>
  );
};

export default CarbonProjectionChart;
