import { useApp } from '../../context/AppContext.jsx';

const STATUS_ICONS = { BLOCKED: '🚫', ALERT: '⚠️', PASS: '✓' };
const RISK_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
const RISK_CLS = { CRITICAL: 'oh-critical', HIGH: 'oh-high', MEDIUM: 'oh-medium', LOW: 'oh-low' };
const LBL_CLS = { CRITICAL: 'oh-lbl-critical', HIGH: 'oh-lbl-high', MEDIUM: 'oh-lbl-medium', LOW: 'oh-lbl-low' };

export default function OrderHeatmap({ orders }) {
  const { dispatch } = useApp();

  const grouped = {};
  for (const risk of RISK_ORDER) grouped[risk] = [];
  for (const o of orders) {
    const r = o.Risk_Level || 'LOW';
    if (!grouped[r]) grouped[r] = [];
    grouped[r].push(o);
  }
  for (const r of RISK_ORDER) {
    grouped[r].sort((a, b) => {
      const so = { BLOCKED: 0, ALERT: 1, PASS: 2 };
      const sd = (so[a.Process_Status] ?? 2) - (so[b.Process_Status] ?? 2);
      if (sd !== 0) return sd;
      return (b.Deviation_Score || 0) - (a.Deviation_Score || 0);
    });
  }

  const hasAny = RISK_ORDER.some((r) => grouped[r].length > 0);
  if (!hasAny) return null;

  return (
    <div className="table-card">
      <div className="table-top">
        <span className="section-title">Order Risk Heatmap</span>
        <span className="section-count">{orders.length} orders</span>
      </div>
      <div className="order-heatmap-body">
        {RISK_ORDER.map((risk) => {
          const group = grouped[risk];
          if (group.length === 0) return null;
          return (
            <div key={risk} className="oh-group">
              <div className={`oh-group-label ${LBL_CLS[risk]}`}>
                {risk}
                <span className="oh-group-count">{group.length}</span>
              </div>
              <div className="oh-tiles">
                {group.map((o) => (
                  <div
                    key={o.Order_Number}
                    className={`oh-tile ${RISK_CLS[risk]}${o.Process_Status === 'BLOCKED' ? ' oh-blocked' : ''}`}
                    onClick={() => dispatch({ type: 'SHOW_DETAIL', payload: o.Order_Number })}
                  >
                    <div className="oh-tile-num">{o.Order_Number}</div>
                    <div className="oh-tile-meta">
                      <span className="oh-tile-icon">{STATUS_ICONS[o.Process_Status] || ''}</span>
                      <span className="oh-tile-status">{o.Process_Status}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
