import { useState, useEffect } from 'react';
import StatusBadge from '../common/StatusBadge.jsx';
import RiskBadge from '../common/RiskBadge.jsx';
import DeviationDots from '../common/DeviationDots.jsx';
import { useApp } from '../../context/AppContext.jsx';

const PAGE_SIZE = 10;

export default function InsightsTable({ orders, label, action }) {
  const { dispatch } = useApp();
  const [page, setPage] = useState(0);

  // Reset to first page when orders change (e.g. filter applied)
  useEffect(() => { setPage(0); }, [orders]);

  if (!orders || orders.length === 0) {
    return (
      <div className="table-card">
        <div className="table-top">
          <span className="section-title">{label || 'Top Risk Orders'}</span>
        </div>
        <div className="empty">
          <div className="empty-icon">✓</div>
          <div className="empty-text">No deviations found — all orders compliant</div>
        </div>
      </div>
    );
  }

  const totalPages = Math.ceil(orders.length / PAGE_SIZE);
  const pageOrders = orders.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="table-card">
      <div className="table-top">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="section-title">{label || 'Top Risk Orders'}</span>
          <span className="section-count">{orders.length}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {action}
          {totalPages > 1 && (
            <div className="pagination">
              <button
                className="page-btn"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
              >
                ‹ Prev
              </button>
              <span className="page-info">
                {page + 1} / {totalPages}
              </span>
              <button
                className="page-btn"
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page === totalPages - 1}
              >
                Next ›
              </button>
            </div>
          )}
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th>Order #</th>
            <th>Status</th>
            <th>Risk</th>
            <th>Score</th>
            <th>Deviations</th>
            <th>Root Cause</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {pageOrders.map((o) => (
            <tr
              key={o.Order_Number}
              onClick={() => dispatch({ type: 'SHOW_DETAIL', payload: o.Order_Number })}
            >
              <td><span className="order-num">{o.Order_Number}</span></td>
              <td><StatusBadge status={o.Process_Status} /></td>
              <td><RiskBadge risk={o.Risk_Level} /></td>
              <td><span className="mono-sm">{o.Deviation_Score ?? '—'}</span></td>
              <td><DeviationDots order={o} /></td>
              <td>
                <span className="root-cause-cell">
                  {o.root_cause || '—'}
                </span>
              </td>
              <td>
                <button
                  className="action-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    dispatch({ type: 'SHOW_DETAIL', payload: o.Order_Number });
                  }}
                >
                  View →
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {totalPages > 1 && (
        <div className="table-footer">
          Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, orders.length)} of {orders.length} orders
        </div>
      )}
    </div>
  );
}
