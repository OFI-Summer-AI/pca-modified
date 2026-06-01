export default function KpiRow({ data }) {
  const summary = data.statusSummary || {};
  const total = data.totalOrders || 0;
  const blocked = summary.BLOCKED || 0;
  const alert = summary.ALERT || 0;
  const pass = summary.PASS || 0;

  const adherence = total > 0 ? Math.round((pass / total) * 100) : 0;
  // Use pre-computed avg from backend summary
  const avgDevs = (data.summary?.avg_deviation_count ?? 0).toFixed(1);
  const nonCompliantPct = total > 0 ? Math.round(((blocked + alert) / total) * 100) : 0;

  return (
    <div className="kpi-row">
      <div className="kpi n">
        <div className="kpi-label">Total Orders</div>
        <div className="kpi-val n">{total}</div>
        <div className="kpi-delta">Analyzed this batch</div>
      </div>
      <div className="kpi l">
        <div className="kpi-label">Adherence Rate</div>
        <div className="kpi-val l">{adherence}%</div>
        <div className="kpi-delta">Compliant orders</div>
      </div>
      <div className="kpi h">
        <div className="kpi-label">Avg Deviations</div>
        <div className="kpi-val h">{avgDevs}</div>
        <div className="kpi-delta">Per order</div>
      </div>
      <div className="kpi m">
        <div className="kpi-label">Throughput</div>
        <div className="kpi-val m">{total}</div>
        <div className="kpi-delta">Orders per batch</div>
      </div>
      <div className="kpi c">
        <div className="kpi-label">Non-Compliant</div>
        <div className="kpi-val c">{nonCompliantPct}%</div>
        <div className="kpi-delta">Blocked + Alert</div>
      </div>
    </div>
  );
}
