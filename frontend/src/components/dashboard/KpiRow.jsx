import { useApp } from '../../context/AppContext.jsx';

const DEV_LABELS = {
  WRONG_SOURCE:          { label: 'Wrong Source',    color: 'critical', icon: '⚠' },
  PLANT_MISMATCH:        { label: 'Plant Mismatch',  color: 'high',     icon: '🏭' },
  DELAYED:               { label: 'Past Due',        color: 'high',     icon: '⏰' },
  DELAY_FLAG:            { label: 'Pre-Flagged',     color: 'medium',   icon: '🚩' },
  MISSING_CRITICAL_STEP: { label: 'Missing Step',    color: 'critical', icon: '✕' },
  OUT_OF_SEQUENCE:       { label: 'Out of Sequence', color: 'high',     icon: '↕' },
  DUPLICATE_STEP:        { label: 'Duplicate Step',  color: 'low',      icon: '⧉' },
};

function getDevLabel(type) {
  return DEV_LABELS[type] || { label: type, color: 'medium', icon: '!' };
}

export default function KpiRow({ data }) {
  const { dispatch } = useApp();
  const summary = data.statusSummary || {};
  const total = data.totalOrders || 0;
  const blocked = summary.BLOCKED || 0;
  const alert = summary.ALERT || 0;
  const pass = summary.PASS || 0;
  const nonCompliant = blocked + alert;

  const adherence = total > 0 ? ((pass / total) * 100).toFixed(1) : '0.0';
  const devTypeCounts = data.deviationTypeCounts || {};

  const gotoAll      = () => dispatch({ type: 'GOTO_ORDERS', status: 'ALL' });
  const gotoPass     = () => dispatch({ type: 'GOTO_ORDERS', status: 'PASS' });
  const gotoBlocked  = () => dispatch({ type: 'GOTO_ORDERS', status: 'BLOCKED' });
  const gotoAlert    = () => dispatch({ type: 'GOTO_ORDERS', status: 'ALERT' });
  const gotoNonComp  = () => {
    // Navigate to BLOCKED first; user can toggle to see ALERT too
    dispatch({ type: 'GOTO_ORDERS', status: 'BLOCKED' });
  };

  return (
    <div className="kpi-section">
      {/* Row 1 — Metric cards */}
      <div className="kpi-row">
        <div className="kpi n kpi-clickable" onClick={gotoAll} title="View all orders">
          <div className="kpi-label">Total Orders</div>
          <div className="kpi-val n">{total.toLocaleString()}</div>
          <div className="kpi-delta">Analysed this batch</div>
          <div className="kpi-cta">View all →</div>
        </div>

        <div className="kpi l kpi-clickable" onClick={gotoPass} title="View compliant orders">
          <div className="kpi-label">Adherence Rate</div>
          <div className="kpi-val l">{adherence}%</div>
          <div className="kpi-delta">{pass.toLocaleString()} compliant orders</div>
          <div className="kpi-cta">View compliant →</div>
        </div>

        <div className="kpi c kpi-clickable" onClick={gotoBlocked} title="View blocked orders">
          <div className="kpi-label">Blocked</div>
          <div className="kpi-val c">{blocked.toLocaleString()}</div>
          <div className="kpi-delta">Critical / high risk</div>
          <div className="kpi-cta">View blocked →</div>
        </div>

        <div className="kpi m kpi-clickable" onClick={gotoAlert} title="View alert orders">
          <div className="kpi-label">Under Alert</div>
          <div className="kpi-val m">{alert.toLocaleString()}</div>
          <div className="kpi-delta">Medium risk deviations</div>
          <div className="kpi-cta">View alerts →</div>
        </div>

        <div className="kpi h kpi-clickable" onClick={gotoNonComp} title="View non-compliant orders">
          <div className="kpi-label">Non-Compliant</div>
          <div className="kpi-val h">{nonCompliant.toLocaleString()}</div>
          <div className="kpi-delta">
            {total > 0 ? ((nonCompliant / total) * 100).toFixed(1) : '0.0'}% of batch
          </div>
          <div className="kpi-cta">View non-compliant →</div>
        </div>
      </div>

      {/* Row 2 — Deviation breakdown pills */}
      {Object.keys(devTypeCounts).length > 0 && (
        <div className="dev-breakdown">
          <div className="dev-breakdown-header">
            <span className="dev-breakdown-title">Deviation Breakdown</span>
            <span className="dev-breakdown-sub">Click any issue to see affected orders</span>
          </div>
          <div className="dev-breakdown-pills">
            {Object.entries(devTypeCounts)
              .sort((a, b) => b[1] - a[1])
              .map(([type, count]) => {
                const { label, color, icon } = getDevLabel(type);
                return (
                  <button
                    key={type}
                    className={`dev-pill dev-pill-${color}`}
                    onClick={() => dispatch({ type: 'GOTO_ORDERS', deviationType: type })}
                    title={`View ${count.toLocaleString()} orders with ${label}`}
                  >
                    <span className="dev-pill-icon">{icon}</span>
                    <span className="dev-pill-label">{label}</span>
                    <span className="dev-pill-count">{count.toLocaleString()}</span>
                    <span className="dev-pill-pct">
                      {total > 0 ? ((count / total) * 100).toFixed(1) : '0'}%
                    </span>
                  </button>
                );
              })}
          </div>
        </div>
      )}

      {/* Row 2 (no deviations) — healthy state message */}
      {Object.keys(devTypeCounts).length === 0 && total > 0 && (
        <div className="dev-breakdown dev-breakdown-healthy">
          <span className="dev-healthy-icon">✓</span>
          <div>
            <div className="dev-breakdown-title" style={{ color: 'var(--pass)' }}>
              All {total.toLocaleString()} orders are fully compliant
            </div>
            <div className="dev-breakdown-sub">
              Every order followed the standard process — no deviations detected.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
