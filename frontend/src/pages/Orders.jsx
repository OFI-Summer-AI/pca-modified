import { useEffect, useRef, useState } from 'react';
import { useApp } from '../context/AppContext.jsx';
import StatusBadge from '../components/common/StatusBadge.jsx';
import RiskBadge from '../components/common/RiskBadge.jsx';
import DeviationDots from '../components/common/DeviationDots.jsx';
import PAM_CONFIG from '../config.js';

function getOrderDate(o) {
  const meta = o.metadata || {};
  const raw = meta.WADAT_IST || meta.actual_date || o.Order_Date || o.first_event_date || '';
  if (!raw) return '';
  try { return new Date(raw).toISOString().split('T')[0]; } catch { return String(raw).slice(0, 10); }
}

const PAGE_LIMIT = 100;

export default function Orders() {
  const { state, dispatch } = useApp();
  const {
    sessionId, statusFilter, riskFilter,
    dateFrom, dateTo, searchQuery,
  } = state;

  const [orders, setOrders] = useState([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef(null);

  // Reset to page 1 whenever filters change
  useEffect(() => { setPage(1); }, [statusFilter, riskFilter, dateFrom, dateTo, searchQuery]);

  useEffect(() => {
    if (!sessionId) return;

    // Cancel any in-flight request
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);

    const params = new URLSearchParams({
      session_id: sessionId,
      page,
      limit: PAGE_LIMIT,
    });
    if (statusFilter && statusFilter !== 'ALL') params.set('status', statusFilter);
    if (riskFilter) params.set('risk', riskFilter);
    if (searchQuery.trim()) params.set('search', searchQuery.trim());
    if (dateFrom) params.set('date_from', dateFrom);
    if (dateTo) params.set('date_to', dateTo);

    fetch(`${PAM_CONFIG.API_BASE}/orders?${params}`, { signal: controller.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`Server error ${r.status}`);
        return r.json();
      })
      .then((data) => {
        setOrders(data.orders || []);
        setTotal(data.total || 0);
        setTotalPages(data.pages || 0);
        setLoading(false);
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setLoading(false);
      });
  }, [sessionId, statusFilter, riskFilter, dateFrom, dateTo, searchQuery, page]);

  const setStatus = (s) => dispatch({ type: 'SET_STATUS_FILTER', payload: s });
  const setRisk = (r) => dispatch({ type: 'SET_RISK_FILTER', payload: r });

  const STATUSES = ['ALL', 'BLOCKED', 'ALERT', 'PASS'];
  const RISKS = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];

  return (
    <div className="page">
      <div className="filters">
        <div className="filter-group">
          {STATUSES.map((s) => (
            <button
              key={s}
              className={`filter-chip${statusFilter === s ? ' active' : ''}`}
              onClick={() => setStatus(s)}
            >
              {s}
            </button>
          ))}
        </div>

        <div className="filter-group">
          {RISKS.map((r) => (
            <button
              key={r}
              className={`filter-chip${riskFilter === r ? ` active ${r.toLowerCase()}` : ''}`}
              onClick={() => setRisk(r)}
            >
              {r}
            </button>
          ))}
        </div>

        <div className="date-filter">
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => dispatch({ type: 'SET_DATE', field: 'dateFrom', payload: e.target.value })}
          />
          <span className="date-filter-sep">→</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => dispatch({ type: 'SET_DATE', field: 'dateTo', payload: e.target.value })}
          />
          {(dateFrom || dateTo) && (
            <button className="date-clear-btn" onClick={() => dispatch({ type: 'CLEAR_DATE' })}>
              Clear
            </button>
          )}
        </div>

        <div className="search-box">
          <input
            type="text"
            placeholder="Order # search…"
            value={searchQuery}
            onChange={(e) => dispatch({ type: 'SET_SEARCH', payload: e.target.value })}
          />
        </div>
      </div>

      <div className="table-card">
        <div className="table-top">
          <span className="section-title">All Orders</span>
          <span className="section-count">
            {loading ? 'Loading…' : `${total.toLocaleString()} total`}
          </span>
        </div>

        {loading && orders.length === 0 ? (
          <div className="empty">
            <div className="empty-text">Loading orders…</div>
          </div>
        ) : orders.length === 0 ? (
          <div className="empty">
            <div className="empty-icon">🔍</div>
            <div className="empty-text">No orders match the current filters</div>
          </div>
        ) : (
          <>
            <table>
              <thead>
                <tr>
                  <th>Order #</th>
                  <th>Date</th>
                  <th>Status</th>
                  <th>Risk</th>
                  <th>Steps</th>
                  <th>Deviations</th>
                  <th>Types</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr
                    key={o.Order_Number}
                    onClick={() => dispatch({ type: 'SHOW_DETAIL', payload: o.Order_Number })}
                  >
                    <td>
                      <div className="order-num">{o.Order_Number}</div>
                      {o.Customer && <div className="customer-sub">{o.Customer}</div>}
                    </td>
                    <td><span className="date-cell">{getOrderDate(o) || '—'}</span></td>
                    <td><StatusBadge status={o.Process_Status} /></td>
                    <td><RiskBadge risk={o.Risk_Level} /></td>
                    <td><span className="mono-sm">{(o.Actual_Flow || []).length}</span></td>
                    <td><DeviationDots order={o} /></td>
                    <td>
                      <span className="dev-types-cell">
                        {(o.Deviations || []).map((d) => d.type).join(', ') || o.Deviation_Types || '—'}
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
                        Detail →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="table-footer" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <button
                  className="page-btn"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1 || loading}
                >
                  ‹ Prev
                </button>
                <span className="page-info">
                  Page {page} / {totalPages} &nbsp;·&nbsp; {total.toLocaleString()} orders
                </span>
                <button
                  className="page-btn"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages || loading}
                >
                  Next ›
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
