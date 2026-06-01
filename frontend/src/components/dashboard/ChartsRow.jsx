import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  ArcElement,
  Tooltip,
  Legend,
} from 'chart.js';
import { Bar, Doughnut } from 'react-chartjs-2';
import { useApp } from '../../context/AppContext.jsx';

ChartJS.register(CategoryScale, LinearScale, BarElement, ArcElement, Tooltip, Legend);

const BAR_COLORS = ['#b02828', '#a05020', '#7a6010', '#3563bf', '#2a7848', '#6a3090'];

export default function ChartsRow({ data }) {
  const { state, dispatch } = useApp();
  const { selectedHeatmapRisk } = state;

  const heatmap = data.heatmap || { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };

  // Use pre-computed deviation type counts (no client-side order iteration needed)
  const devTypeCounts = data.deviationTypeCounts || {};
  const devLabels = Object.keys(devTypeCounts);
  const devValues = Object.values(devTypeCounts);

  const barData = {
    labels: devLabels,
    datasets: [
      {
        label: 'Count',
        data: devValues,
        backgroundColor: devLabels.map((_, i) => BAR_COLORS[i % BAR_COLORS.length]),
        borderRadius: 4,
      },
    ],
  };

  const barOptions = {
    responsive: true,
    plugins: { legend: { display: false }, tooltip: { mode: 'index' } },
    scales: {
      x: { grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 30 } },
      y: { grid: { color: '#edf0f5' }, ticks: { font: { size: 10 } }, beginAtZero: true },
    },
  };

  const donutData = {
    labels: ['Critical', 'High', 'Medium', 'Low'],
    datasets: [
      {
        data: [heatmap.CRITICAL, heatmap.HIGH, heatmap.MEDIUM, heatmap.LOW],
        backgroundColor: ['#b02828', '#a05020', '#7a6010', '#2a7848'],
        borderWidth: 2,
        borderColor: '#ffffff',
      },
    ],
  };

  const donutOptions = {
    responsive: true,
    plugins: {
      legend: { position: 'right', labels: { font: { size: 11 }, boxWidth: 12, padding: 10 } },
    },
    cutout: '68%',
  };

  const cells = [
    { key: 'CRITICAL', label: 'Critical', cls: 'critical' },
    { key: 'HIGH', label: 'High', cls: 'high' },
    { key: 'MEDIUM', label: 'Medium', cls: 'medium' },
    { key: 'LOW', label: 'Low', cls: 'low' },
  ];

  const toggleRisk = (key) => dispatch({ type: 'TOGGLE_HEATMAP_RISK', payload: key });

  return (
    <div className="charts-row">
      <div className="chart-card">
        <div className="chart-title">Deviation Type Breakdown</div>
        {devLabels.length > 0 ? (
          <Bar data={barData} options={barOptions} />
        ) : (
          <div className="empty">
            <div className="empty-icon">📊</div>
            <div className="empty-text">No deviations to chart</div>
          </div>
        )}
      </div>

      <div className="chart-card">
        <div className="chart-title">Risk Distribution</div>
        <Doughnut data={donutData} options={donutOptions} />
      </div>

      <div className="chart-card">
        <div className="chart-title">Risk Heatmap</div>
        <div className="heatmap-grid">
          {cells.map(({ key, label, cls }) => (
            <div
              key={key}
              className={`heatmap-cell ${cls}${selectedHeatmapRisk === key ? ' active' : ''}`}
              onClick={() => toggleRisk(key)}
            >
              <div className="heatmap-num">{heatmap[key] || 0}</div>
              <div className="heatmap-lbl">{label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
