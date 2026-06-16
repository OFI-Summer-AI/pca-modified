import {
  Chart as ChartJS,
  CategoryScale, LinearScale,
  LineElement, PointElement,
  ArcElement,
  Filler, Tooltip, Legend,
} from 'chart.js';
import { Line, Doughnut } from 'react-chartjs-2';
import { useApp } from '../../context/AppContext.jsx';

ChartJS.register(
  CategoryScale, LinearScale,
  LineElement, PointElement,
  ArcElement,
  Filler, Tooltip, Legend,
);

const DEV_DISPLAY = {
  WRONG_SOURCE:          'Wrong Source',
  PLANT_MISMATCH:        'Plant Mismatch',
  DELAYED:               'Past Due',
  DELAY_FLAG:            'Pre-Flagged',
  MISSING_CRITICAL_STEP: 'Missing Step',
  OUT_OF_SEQUENCE:       'Out of Sequence',
  DUPLICATE_STEP:        'Duplicate Step',
};

function formatPeriod(p) {
  const [year, month] = p.split('-');
  const names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${names[parseInt(month, 10) - 1]} ${year}`;
}

// ── Trend Line Chart ─────────────────────────────────────────────────────────
function TrendChart({ trendData }) {
  if (!trendData || trendData.length < 2) {
    return (
      <div className="empty" style={{ minHeight: 160 }}>
        <div className="empty-icon" style={{ fontSize: 24 }}>📈</div>
        <div className="empty-text">Not enough date data for trend analysis</div>
      </div>
    );
  }

  const labels       = trendData.map((d) => formatPeriod(d.period));
  const compliant    = trendData.map((d) => d.compliant);
  const nonCompliant = trendData.map((d) => d.non_compliant);

  const chartData = {
    labels,
    datasets: [
      {
        label: 'Compliant',
        data: compliant,
        borderColor: 'rgba(42,120,72,0.9)',
        backgroundColor: 'rgba(42,120,72,0.07)',
        fill: true,
        tension: 0.35,
        pointRadius: trendData.length > 18 ? 2 : 4,
        pointHoverRadius: 6,
        borderWidth: 2,
      },
      {
        label: 'Non-Compliant',
        data: nonCompliant,
        borderColor: 'rgba(192,50,30,0.9)',
        backgroundColor: 'rgba(192,50,30,0.07)',
        fill: true,
        tension: 0.35,
        pointRadius: trendData.length > 18 ? 2 : 4,
        pointHoverRadius: 6,
        borderWidth: 2,
      },
    ],
  };

  const options = {
    responsive: true,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        position: 'top',
        align: 'end',
        labels: { font: { size: 11 }, boxWidth: 12, padding: 12, usePointStyle: true },
      },
      tooltip: {
        callbacks: {
          label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.y.toLocaleString()} orders`,
        },
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { font: { size: 10 }, maxTicksLimit: 12, maxRotation: 30 },
      },
      y: {
        grid: { color: '#edf0f5' },
        ticks: {
          font: { size: 10 },
          callback: (v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v,
        },
        beginAtZero: true,
      },
    },
  };

  return <Line data={chartData} options={options} />;
}

// ── Deviation Breakdown — interactive donut ───────────────────────────────────
const DEV_COLORS = [
  'rgba(192,50,30,0.88)',
  'rgba(210,100,20,0.88)',
  'rgba(204,162,63,0.88)',
  'rgba(130,70,180,0.88)',
  'rgba(30,110,190,0.88)',
  'rgba(30,140,100,0.88)',
  'rgba(160,60,90,0.88)',
];
const DEV_HOVER = [
  'rgba(192,50,30,1)',
  'rgba(210,100,20,1)',
  'rgba(204,162,63,1)',
  'rgba(130,70,180,1)',
  'rgba(30,110,190,1)',
  'rgba(30,140,100,1)',
  'rgba(160,60,90,1)',
];

// Center-text plugin — shows total inside the donut hole
const centerTextPlugin = {
  id: 'centerText',
  afterDraw(chart) {
    const { ctx, chartArea } = chart;
    if (!chartArea) return;
    const cx = (chartArea.left + chartArea.right) / 2;
    const cy = (chartArea.top  + chartArea.bottom) / 2;
    const total = chart.data.datasets[0].data.reduce((s, v) => s + v, 0);
    ctx.save();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = 'bold 20px DM Sans, sans-serif';
    ctx.fillStyle = '#242424';
    ctx.fillText(total >= 1000 ? `${(total / 1000).toFixed(1)}k` : String(total), cx, cy - 10);
    ctx.font = '11px DM Sans, sans-serif';
    ctx.fillStyle = '#999';
    ctx.fillText('non-compliant', cx, cy + 12);
    ctx.restore();
  },
};

function DeviationBreakdown({ heatmapGrid }) {
  const { dispatch } = useApp();

  const devTypes = Object.keys(heatmapGrid || {});
  if (!devTypes.length) {
    return (
      <div className="empty" style={{ minHeight: 160 }}>
        <div className="empty-icon" style={{ fontSize: 22 }}>✓</div>
        <div className="empty-text">No deviations detected</div>
      </div>
    );
  }

  // Total orders per deviation type (sum across all risk levels)
  const totals = devTypes.map((dt) =>
    Object.values(heatmapGrid[dt] || {}).reduce((s, v) => s + v, 0)
  );

  const chartData = {
    labels: devTypes.map((t) => DEV_DISPLAY[t] || t),
    datasets: [{
      data: totals,
      backgroundColor: DEV_COLORS.slice(0, devTypes.length),
      hoverBackgroundColor: DEV_HOVER.slice(0, devTypes.length),
      borderWidth: 2,
      borderColor: '#fff',
      hoverOffset: 8,
    }],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '62%',
    plugins: {
      legend: {
        position: 'right',
        labels: {
          color: '#555',
          font: { size: 11 },
          usePointStyle: true,
          pointStyleWidth: 10,
          padding: 14,
          generateLabels: (chart) =>
            chart.data.labels.map((label, i) => ({
              text: `${label}  ${totals[i].toLocaleString()}`,
              fillStyle: DEV_COLORS[i] || '#ccc',
              hidden: false,
              index: i,
            })),
        },
      },
      tooltip: {
        callbacks: {
          label: (ctx) => {
            const val = ctx.raw;
            const sum = ctx.dataset.data.reduce((s, v) => s + v, 0);
            const pct = sum ? ((val / sum) * 100).toFixed(1) : 0;
            return `  ${val.toLocaleString()} orders (${pct}%)`;
          },
        },
      },
    },
    onClick: (_, elements) => {
      if (!elements.length) return;
      const idx = elements[0].index;
      dispatch({ type: 'GOTO_ORDERS', deviationType: devTypes[idx] });
    },
  };

  return (
    <div style={{ height: 230, cursor: 'pointer' }}>
      <Doughnut data={chartData} options={options} plugins={[centerTextPlugin]} />
    </div>
  );
}

// ── Main export ──────────────────────────────────────────────────────────────
export default function ChartsRow({ data }) {
  const trendData   = data.trendData   || [];
  const heatmapGrid = data.heatmapGrid || {};

  return (
    <div className="charts-row-2">
      {/* Trend analysis */}
      <div className="chart-card">
        <div className="chart-title-row">
          <span className="chart-title">Order Compliance Trend</span>
          <span className="chart-subtitle">Monthly — Compliant vs Non-Compliant</span>
        </div>
        <TrendChart trendData={trendData} />
      </div>

      {/* Donut deviation breakdown */}
      <div className="chart-card">
        <div className="chart-title-row">
          <span className="chart-title">Deviation Distribution</span>
          <span className="chart-subtitle">Non-compliant orders by issue type — click to drill down</span>
        </div>
        <DeviationBreakdown heatmapGrid={heatmapGrid} />
      </div>
    </div>
  );
}
