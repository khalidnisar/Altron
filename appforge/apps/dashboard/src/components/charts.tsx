'use client';

import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';

const AXIS = { stroke: '#8B93A7', fontSize: 11 };
const GRID = '#252B3B';

const TOOLTIP_STYLE = {
  backgroundColor: '#1B2030',
  border: '1px solid #252B3B',
  borderRadius: 8,
  fontSize: 12,
  color: '#E8EAF2',
};

function shortDate(value: string) {
  const d = new Date(value);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export function RevenueChart({ data }: {
  data: { date: string; revenue: number }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <defs>
          <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#5C7CFA" stopOpacity={0.5} />
            <stop offset="100%" stopColor="#5C7CFA" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="date" tickFormatter={shortDate} {...AXIS} tickLine={false} />
        <YAxis {...AXIS} tickLine={false} axisLine={false}
               tickFormatter={(v) => `$${v}`} />
        <Tooltip contentStyle={TOOLTIP_STYLE}
                 formatter={(v: number) => [`$${v.toFixed(2)}`, 'Revenue']} />
        <Area type="monotone" dataKey="revenue" stroke="#5C7CFA" strokeWidth={2}
              fill="url(#rev)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function StreamChart({ data }: {
  data: { date: string; ad_revenue: number; iap_revenue: number; subscription_revenue: number }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="date" tickFormatter={shortDate} {...AXIS} tickLine={false} />
        <YAxis {...AXIS} tickLine={false} axisLine={false} tickFormatter={(v) => `$${v}`} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="ad_revenue" name="Ads" stackId="a" fill="#5C7CFA" />
        <Bar dataKey="iap_revenue" name="IAP" stackId="a" fill="#22C55E" />
        <Bar dataKey="subscription_revenue" name="Subscriptions" stackId="a" fill="#F59E0B" />
      </BarChart>
    </ResponsiveContainer>
  );
}

const PIE_COLORS = ['#5C7CFA', '#22C55E', '#F59E0B', '#EC4899', '#8B5CF6', '#0EA5E9'];

export function AppSplitChart({ data }: { data: { name: string; value: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={60} outerRadius={100}
             paddingAngle={2}>
          {data.map((_, i) => (
            <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
          ))}
        </Pie>
        <Tooltip contentStyle={TOOLTIP_STYLE}
                 formatter={(v: number) => `$${v.toFixed(2)}`} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}
