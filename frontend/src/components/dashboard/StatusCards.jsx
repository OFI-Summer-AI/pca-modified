import { useApp } from '../../context/AppContext.jsx';

export default function StatusCards({ data }) {
  const { dispatch } = useApp();
  const s = data.statusSummary || {};
  const blocked = s.BLOCKED || 0;
  const alert   = s.ALERT   || 0;
  const pass    = s.PASS    || 0;

  const goto = (status) => dispatch({ type: 'GOTO_ORDERS', status });

  return (
    <div className="status-row">
      <div className="status-card status-card-clickable" onClick={() => goto('BLOCKED')} title="View all blocked orders">
        <div className="status-icon blocked">🚫</div>
        <div>
          <div className="status-num blocked">{blocked.toLocaleString()}</div>
          <div className="status-label">Orders Blocked</div>
        </div>
        <div className="status-card-arrow">→</div>
      </div>

      <div className="status-card status-card-clickable" onClick={() => goto('ALERT')} title="View all alert orders">
        <div className="status-icon alert">⚠</div>
        <div>
          <div className="status-num alert">{alert.toLocaleString()}</div>
          <div className="status-label">Under Alert</div>
        </div>
        <div className="status-card-arrow">→</div>
      </div>

      <div className="status-card status-card-clickable" onClick={() => goto('PASS')} title="View all compliant orders">
        <div className="status-icon pass">✓</div>
        <div>
          <div className="status-num pass">{pass.toLocaleString()}</div>
          <div className="status-label">Compliant</div>
        </div>
        <div className="status-card-arrow">→</div>
      </div>
    </div>
  );
}
