function getDeviationCounts(order) {
  const counts = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
  const devs = order.Deviations || order.Deviations_Array || [];
  for (const d of devs) {
    const sev = d.severity || d.Severity || '';
    if (counts[sev] !== undefined) counts[sev]++;
  }
  return counts;
}

export default function DeviationDots({ order }) {
  const counts = getDeviationCounts(order);
  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  if (total === 0) return <span className="no-dev">None</span>;

  const dots = [];
  const map = [['CRITICAL', 'c'], ['HIGH', 'h'], ['MEDIUM', 'm'], ['LOW', 'l']];
  for (const [sev, cls] of map) {
    for (let i = 0; i < counts[sev]; i++) {
      dots.push(<span key={`${sev}-${i}`} className={`dev-dot ${cls}`} />);
    }
  }

  return <div className="deviation-bar">{dots}</div>;
}
