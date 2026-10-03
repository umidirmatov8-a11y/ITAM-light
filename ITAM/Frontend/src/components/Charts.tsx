import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Empty } from 'antd';
import { useThemeMode } from '@/theme/theme';

export interface Point { label: string; value: number; color?: string | null }

/** Validated reference palette (slot 1 for single-series charts), light/dark steps. */
const SERIES_1 = { light: '#2a78d6', dark: '#3987e5' };

/** Single-series bar chart: thin bars, rounded data ends, recessive grid, hover tooltip. */
export function BarChartCard({ data, horizontal, height = 260, useItemColors }: { data?: Point[]; horizontal?: boolean; height?: number; useItemColors?: boolean }) {
  const { mode } = useThemeMode();
  if (!data || data.length === 0) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  const ink = mode === 'dark' ? '#c3c2b7' : '#52514e';
  const grid = mode === 'dark' ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';
  const fill = SERIES_1[mode];
  const tooltipStyle = { background: mode === 'dark' ? '#1a1a19' : '#fff', border: `1px solid ${grid}`, borderRadius: 8, color: mode === 'dark' ? '#fff' : '#0b0b0b' };
  return (
    <ResponsiveContainer width="100%" height={horizontal ? Math.max(height, data.length * 30 + 40) : height}>
      <BarChart data={data} layout={horizontal ? 'vertical' : 'horizontal'} margin={{ top: 8, right: 16, left: horizontal ? 8 : -12, bottom: 4 }} barCategoryGap={horizontal ? 6 : '20%'}>
        <CartesianGrid stroke={grid} vertical={!!horizontal} horizontal={!horizontal} />
        {horizontal ? (
          <>
            <XAxis type="number" allowDecimals={false} tick={{ fill: ink, fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="label" width={150} tick={{ fill: ink, fontSize: 12 }} axisLine={false} tickLine={false} />
          </>
        ) : (
          <>
            <XAxis dataKey="label" tick={{ fill: ink, fontSize: 12 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
            <YAxis allowDecimals={false} tick={{ fill: ink, fontSize: 12 }} axisLine={false} tickLine={false} />
          </>
        )}
        <Tooltip cursor={{ fill: grid }} contentStyle={tooltipStyle} labelStyle={{ color: tooltipStyle.color }} itemStyle={{ color: tooltipStyle.color }} />
        <Bar dataKey="value" fill={fill} radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false}>
          {useItemColors && data.map((d, i) => <Cell key={i} fill={d.color || fill} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
