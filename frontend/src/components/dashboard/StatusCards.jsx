export default function StatusCards({ data }) {
  const s = data.statusSummary || {};
  const blocked = s.BLOCKED || 0;
  const alert = s.ALERT || 0;
  const pass = s.PASS || 0;

  return (
    <div className="status-row">
      <div className="status-card">
        <div className="status-icon blocked">🚫</div>
        <div>
          <div className="status-num blocked">{blocked}</div>
          <div className="status-label">Orders Blocked</div>
        </div>
      </div>
      <div className="status-card">
        <div className="status-icon alert">⚠️</div>
        <div>
          <div className="status-num alert">{alert}</div>
          <div className="status-label">Under Alert</div>
        </div>
      </div>
      <div className="status-card">
        <div className="status-icon pass">✓</div>
        <div>
          <div className="status-num pass">{pass}</div>
          <div className="status-label">Compliant</div>
        </div>
      </div>
    </div>
  );
}
