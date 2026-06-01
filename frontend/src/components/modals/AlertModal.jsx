import { useState } from 'react';
import { useApp } from '../../context/AppContext.jsx';
import StatusBadge from '../common/StatusBadge.jsx';
import RiskBadge from '../common/RiskBadge.jsx';
import PAM_CONFIG from '../../config.js';

export default function AlertModal() {
  const { state, dispatch } = useApp();
  const { appData } = state;
  const [tiers, setTiers] = useState({ CRITICAL: true, HIGH: true, MEDIUM: false });
  const [sending, setSending] = useState(false);

  const heatmap = appData?.heatmap || {};
  // Use pre-computed top orders per risk level (no full orders array needed)
  const riskTopOrders = appData?.riskTopOrders || {};

  const targets = [
    ...(tiers.CRITICAL ? (riskTopOrders.CRITICAL || []) : []),
    ...(tiers.HIGH ? (riskTopOrders.HIGH || []) : []),
    ...(tiers.MEDIUM ? (riskTopOrders.MEDIUM || []) : []),
  ];

  const toggleTier = (tier) => setTiers((prev) => ({ ...prev, [tier]: !prev[tier] }));

  const send = async () => {
    setSending(true);
    try {
      await fetch(`${PAM_CONFIG.API_BASE}/send-alerts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ orders: targets }),
      });
      dispatch({ type: 'CLOSE_ALERT_MODAL' });
      dispatch({ type: 'SHOW_TOAST', message: `Alert emails sent for ${targets.length} orders`, toastType: 'success' });
    } catch {
      dispatch({ type: 'SHOW_TOAST', message: 'Failed to send alerts', toastType: 'error' });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && dispatch({ type: 'CLOSE_ALERT_MODAL' })}>
      <div className="modal">
        <button className="modal-close" onClick={() => dispatch({ type: 'CLOSE_ALERT_MODAL' })}>✕</button>
        <div className="modal-title">Send Risk Alerts</div>
        <div className="modal-sub">Select which risk tiers to notify — {targets.length} order(s) selected</div>

        <div className="alert-tier-toggles">
          {[
            { key: 'CRITICAL', note: 'includes BLOCKED status' },
            { key: 'HIGH', note: '' },
            { key: 'MEDIUM', note: '' },
          ].map(({ key, note }) => (
            <label key={key} className={`tier-toggle ${key}`}>
              <input
                type="checkbox"
                checked={tiers[key]}
                onChange={() => toggleTier(key)}
              />
              <span className="tier-toggle-label">{key} Risk</span>
              {note && <span className="tier-toggle-note">{note}</span>}
              <span className="tier-toggle-count">{heatmap[key] || 0}</span>
            </label>
          ))}
        </div>

        <div className="modal-list">
          {targets.length === 0 && (
            <div style={{ color: 'var(--text3)', fontSize: 13, padding: '12px 0', textAlign: 'center' }}>
              No orders match selected tiers
            </div>
          )}
          {targets.map((o) => (
            <div key={o.Order_Number} className="modal-order-item">
              <span className="modal-order-num">{o.Order_Number}</span>
              <span className="modal-customer">{o.Customer || '—'}</span>
              <RiskBadge risk={o.Risk_Level} />
              <StatusBadge status={o.Process_Status} />
            </div>
          ))}
        </div>

        <button
          className="modal-send-btn"
          onClick={send}
          disabled={targets.length === 0 || sending}
        >
          {sending ? 'Sending…' : `📧 Send Alert Emails (${targets.length})`}
        </button>
      </div>
    </div>
  );
}
