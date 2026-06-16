import { useEffect, useRef, useState } from 'react';
import { useApp } from '../context/AppContext.jsx';
import StatusBadge from '../components/common/StatusBadge.jsx';
import RiskBadge from '../components/common/RiskBadge.jsx';
import DeviationDots from '../components/common/DeviationDots.jsx';
import PAM_CONFIG from '../config.js';

const DEV_LABELS_FULL = {
  WRONG_SOURCE:          'Wrong Source',
  PLANT_MISMATCH:        'Plant Mismatch',
  DELAYED:               'Past Due',
  DELAY_FLAG:            'Pre-Flagged',
  MISSING_CRITICAL_STEP: 'Missing Step',
  OUT_OF_SEQUENCE:       'Out of Sequence',
  DUPLICATE_STEP:        'Duplicate Step',
};

// ── Contextual alert email modal ───────────────────────────────────────────────
function OrdersAlertModal({ filterCtx, onClose }) {
  const { state } = useApp();
  const [loading, setLoading]   = useState(true);
  const [preview, setPreview]   = useState(null);
  const [sending, setSending]   = useState(false);
  const [status,  setStatus]    = useState(null);

  useEffect(() => {
    setLoading(true);
    setStatus(null);
    const p = new URLSearchParams({ session_id: state.sessionId, order_count: String(filterCtx.orderCount) });
    if (filterCtx.deviationType)  p.set('deviation_type', filterCtx.deviationType);
    if (filterCtx.groupKey)       p.set('group_key', filterCtx.groupKey);
    if (filterCtx.statusFilter && filterCtx.statusFilter !== 'ALL') p.set('status', filterCtx.statusFilter);
    if (filterCtx.riskFilter)     p.set('risk', filterCtx.riskFilter);
    if (filterCtx.intersectionLabels?.length) {
      filterCtx.intersectionLabels.forEach((l) => p.append('filters', l));
    }
    fetch(`${PAM_CONFIG.API_BASE}/compliance/orders-alert-preview?${p}`)
      .then((r) => r.json())
      .then((d) => { setPreview(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSend = async () => {
    setSending(true);
    setStatus(null);
    try {
      const body = {
        session_id: state.sessionId,
        order_count: filterCtx.orderCount,
        deviation_type: filterCtx.deviationType || null,
        group_key: filterCtx.groupKey || null,
        intersection_filters: filterCtx.intersectionLabels || [],
        status: filterCtx.statusFilter !== 'ALL' ? filterCtx.statusFilter : null,
        risk: filterCtx.riskFilter || null,
      };
      const res  = await fetch(`${PAM_CONFIG.API_BASE}/compliance/orders-alert-send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      setStatus(data.status);
      if (data.html_body) setPreview((p) => ({ ...p, ...data }));
    } catch {
      setStatus('error');
    } finally {
      setSending(false);
    }
  };

  // Build a human-readable context label for the modal header
  let contextLabel = 'Current Filter View';
  if (filterCtx.intersectionLabels?.length >= 2) {
    contextLabel = `Cross-Filter: ${filterCtx.intersectionLabels.map((f) => {
      const [t, ...rest] = f.split(':');
      return `${DEV_LABELS_FULL[t] || t}: ${rest.join(':')}`;
    }).join(' + ')}`;
  } else if (filterCtx.groupKey && filterCtx.deviationType) {
    contextLabel = `${DEV_LABELS_FULL[filterCtx.deviationType] || filterCtx.deviationType}: ${filterCtx.groupKey}`;
  } else if (filterCtx.deviationType) {
    contextLabel = `All ${DEV_LABELS_FULL[filterCtx.deviationType] || filterCtx.deviationType} orders`;
  } else if (filterCtx.statusFilter && filterCtx.statusFilter !== 'ALL') {
    contextLabel = `${filterCtx.statusFilter} orders`;
  } else if (filterCtx.riskFilter) {
    contextLabel = `${filterCtx.riskFilter} risk orders`;
  }

  return (
    <div className="email-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="email-modal email-modal-wide">
        <div className="email-modal-hdr">
          <div>
            <span className="email-modal-title">Alert Email Preview</span>
            <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 2 }}>{contextLabel} · {filterCtx.orderCount.toLocaleString()} orders</div>
          </div>
          <button className="email-modal-x" onClick={onClose}>✕</button>
        </div>

        {loading ? (
          <div className="email-modal-loading">Building OFI email template…</div>
        ) : preview ? (
          <>
            <div className="email-meta">
              {preview.recipient && (
                <div className="email-meta-row">
                  <span className="email-meta-k">To:</span>
                  <span className="email-meta-v">{preview.recipient}</span>
                </div>
              )}
              <div className="email-meta-row">
                <span className="email-meta-k">Subject:</span>
                <span className="email-meta-v">{preview.subject}</span>
              </div>
              {!preview.smtp_configured && (
                <div className="email-meta-row">
                  <span className="email-meta-k" style={{ color: 'var(--accent2)' }}>SMTP:</span>
                  <span className="email-meta-v" style={{ color: '#888' }}>
                    Not configured — set SMTP_USER / SMTP_PASS / ALERT_TO_EMAIL in .env
                  </span>
                </div>
              )}
            </div>
            <div className="email-body-wrap">
              {preview.html_body ? (
                <iframe
                  srcDoc={preview.html_body}
                  title="Email Preview"
                  style={{ width: '100%', height: '460px', border: 'none', borderRadius: 4 }}
                  sandbox="allow-same-origin"
                />
              ) : (
                <pre className="email-body-pre">{preview.body}</pre>
              )}
            </div>
          </>
        ) : (
          <div className="email-modal-loading">Failed to build template</div>
        )}

        <div className="email-modal-ftr">
          <div className="email-status-msg">
            {status === 'sent'    && <span className="email-ok">✓ Email sent successfully</span>}
            {status === 'no_smtp' && <span className="email-warn">SMTP not configured — add credentials to .env</span>}
            {status === 'error'   && <span className="email-err">Send failed — check SMTP settings in .env</span>}
          </div>
          <div className="email-modal-btns">
            <button
              className="email-send-btn"
              onClick={handleSend}
              disabled={sending || !preview || status === 'sent'}
            >
              {sending ? 'Sending…' : 'Send Alert Email'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

const DEV_LABELS = {
  WRONG_SOURCE:          'Wrong Source',
  PLANT_MISMATCH:        'Plant Mismatch',
  DELAYED:               'Past Due',
  DELAY_FLAG:            'Pre-Flagged',
  MISSING_CRITICAL_STEP: 'Missing Step',
  OUT_OF_SEQUENCE:       'Out of Sequence',
  DUPLICATE_STEP:        'Duplicate Step',
};

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
    sessionId, statusFilter, riskFilter, deviationTypeFilter, sourceFilter,
    groupKeyFilter, intersectionOrderIds, intersectionLabels,
    dateFrom, dateTo, searchQuery, appData,
  } = state;

  const [alertModal, setAlertModal] = useState(false);

  const [orders, setOrders]         = useState([]);
  const [total, setTotal]           = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [page, setPage]             = useState(1);
  const [loading, setLoading]       = useState(false);
  const abortRef = useRef(null);

  // Deviation type options from pipeline output — only types that actually have orders
  const devTypeCounts = appData?.deviationTypeCounts || {};

  // Heatmap counts for showing order count on risk chips
  const heatmap = appData?.heatmap || {};
  const statusSummary = appData?.statusSummary || {};

  // Reset to page 1 whenever filters change
  useEffect(() => { setPage(1); }, [statusFilter, riskFilter, deviationTypeFilter, sourceFilter, groupKeyFilter, intersectionOrderIds, dateFrom, dateTo, searchQuery]);

  useEffect(() => {
    if (!sessionId) return;

    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);

    const params = new URLSearchParams({ session_id: sessionId, page, limit: PAGE_LIMIT });
    if (statusFilter && statusFilter !== 'ALL') params.set('status', statusFilter);
    if (riskFilter)           params.set('risk', riskFilter);
    if (deviationTypeFilter)  params.set('deviation_type', deviationTypeFilter);
    if (groupKeyFilter)       params.set('group_key', groupKeyFilter);
    if (sourceFilter)         params.set('source_location', sourceFilter);
    if (searchQuery.trim())   params.set('search', searchQuery.trim());
    if (dateFrom)             params.set('date_from', dateFrom);
    if (dateTo)               params.set('date_to', dateTo);
    if (intersectionOrderIds && intersectionOrderIds.length > 0) {
      intersectionOrderIds.forEach((id) => params.append('order_ids', id));
    }

    fetch(`${PAM_CONFIG.API_BASE}/orders?${params}`, { signal: controller.signal })
      .then((r) => { if (!r.ok) throw new Error(`Server error ${r.status}`); return r.json(); })
      .then((data) => {
        setOrders(data.orders || []);
        setTotal(data.total || 0);
        setTotalPages(data.pages || 0);
        setLoading(false);
      })
      .catch((err) => { if (err.name !== 'AbortError') setLoading(false); });
  }, [sessionId, statusFilter, riskFilter, deviationTypeFilter, sourceFilter, groupKeyFilter, intersectionOrderIds, dateFrom, dateTo, searchQuery, page]);

  const setStatus   = (s) => dispatch({ type: 'SET_STATUS_FILTER',    payload: s });
  const setRisk     = (r) => dispatch({ type: 'SET_RISK_FILTER',      payload: r });
  const clearDev         = ()  => dispatch({ type: 'SET_DEVIATION_FILTER', payload: null });
  const clearSource      = ()  => dispatch({ type: 'SET_SOURCE_FILTER',    payload: null });
  const clearGroupKey    = ()  => dispatch({ type: 'GOTO_ORDERS', deviationType: deviationTypeFilter });
  const clearIntersection = () => dispatch({ type: 'GOTO_ORDERS' });

  const STATUSES = ['ALL', 'BLOCKED', 'ALERT', 'PASS'];
  const RISKS = [
    { key: 'CRITICAL', count: heatmap.CRITICAL || 0 },
    { key: 'HIGH',     count: heatmap.HIGH     || 0 },
    { key: 'MEDIUM',   count: heatmap.MEDIUM   || 0 },
    { key: 'LOW',      count: heatmap.LOW      || 0 },
  ];

  const statusCounts = {
    ALL:     (statusSummary.BLOCKED || 0) + (statusSummary.ALERT || 0) + (statusSummary.PASS || 0),
    BLOCKED: statusSummary.BLOCKED || 0,
    ALERT:   statusSummary.ALERT   || 0,
    PASS:    statusSummary.PASS    || 0,
  };

  const activeFilterCount = [
    statusFilter !== 'ALL',
    !!riskFilter,
    !!deviationTypeFilter,
    !!groupKeyFilter,
    !!intersectionOrderIds,
    !!sourceFilter,
    !!searchQuery.trim(),
    !!dateFrom || !!dateTo,
  ].filter(Boolean).length;

  return (
    <div className="page">

      {/* ── Filter bar ─────────────────────────────────────── */}
      <div className="filters-bar">
        {/* Status chips */}
        <div className="filter-group">
          {STATUSES.map((s) => (
            <button
              key={s}
              className={`filter-chip${statusFilter === s ? ' active' : ''}`}
              onClick={() => setStatus(s)}
            >
              {s}
              {statusCounts[s] > 0 && (
                <span className="filter-chip-count">{statusCounts[s].toLocaleString()}</span>
              )}
            </button>
          ))}
        </div>

        {/* Risk chips with order counts */}
        <div className="filter-group">
          {RISKS.map(({ key, count }) => (
            <button
              key={key}
              className={`filter-chip${riskFilter === key ? ` active ${key.toLowerCase()}` : ''}${count === 0 ? ' chip-empty' : ''}`}
              onClick={() => setRisk(key)}
              title={count === 0 ? `No ${key} risk orders in this batch` : `${count.toLocaleString()} ${key} risk orders`}
            >
              {key}
              <span className="filter-chip-count">{count.toLocaleString()}</span>
            </button>
          ))}
        </div>

        {/* Deviation type dropdown — populated from actual data, only shows types with orders */}
        {Object.keys(devTypeCounts).length > 0 && (
          <select
            className="dev-type-select"
            value={deviationTypeFilter || ''}
            onChange={(e) => dispatch({
              type: 'SET_DEVIATION_FILTER',
              payload: e.target.value || null,
            })}
          >
            <option value="">All Issue Types</option>
            {Object.entries(devTypeCounts)
              .sort((a, b) => b[1] - a[1])
              .map(([type, count]) => (
                <option key={type} value={type}>
                  {DEV_LABELS[type] || type}  ({count.toLocaleString()} orders)
                </option>
              ))}
          </select>
        )}

        {/* Active source location filter (set from leaderboard) */}
        {sourceFilter && (
          <div className="filter-group">
            <span className="active-dev-chip active-source-chip">
              <span className="active-dev-label">Source: {sourceFilter}</span>
              <button className="active-dev-clear" onClick={clearSource} title="Clear source filter">
                ✕
              </button>
            </span>
          </div>
        )}

        {/* Date range */}
        <div className="date-filter">
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => dispatch({ type: 'SET_DATE', field: 'dateFrom', payload: e.target.value })}
          />
          <span className="date-filter-sep">to</span>
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

        {/* Search */}
        <div className="search-box">
          <input
            type="text"
            placeholder="Order # search…"
            value={searchQuery}
            onChange={(e) => dispatch({ type: 'SET_SEARCH', payload: e.target.value })}
          />
        </div>

        {/* Clear all filters */}
        {activeFilterCount > 0 && (
          <button
            className="clear-all-btn"
            onClick={() => dispatch({ type: 'GOTO_ORDERS' })}
          >
            Clear all ({activeFilterCount})
          </button>
        )}
      </div>

      {/* ── Orders table ───────────────────────────────────── */}
      <div className="table-card">
        <div className="table-top">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', flex: 1 }}>
            <span className="section-title">
              {intersectionOrderIds
                ? `Cross-Filter Match`
                : groupKeyFilter && deviationTypeFilter
                  ? `${DEV_LABELS[deviationTypeFilter] || deviationTypeFilter} — ${groupKeyFilter}`
                  : sourceFilter && deviationTypeFilter
                    ? `${DEV_LABELS[deviationTypeFilter] || deviationTypeFilter} from ${sourceFilter}`
                    : sourceFilter
                      ? `Orders from Source ${sourceFilter}`
                      : deviationTypeFilter
                        ? `${DEV_LABELS[deviationTypeFilter] || deviationTypeFilter} Orders`
                        : riskFilter
                          ? `${riskFilter} Risk Orders`
                          : statusFilter !== 'ALL'
                            ? `${statusFilter} Orders`
                            : 'All Orders'}
            </span>
            <span className="section-count">
              {loading ? 'Loading…' : `${total.toLocaleString()} total`}
            </span>
            {intersectionOrderIds && (
              <span className="active-dev-chip" style={{ fontSize: 11 }}>
                All selected issues simultaneously
                <button className="active-dev-clear" onClick={clearIntersection}>✕</button>
              </span>
            )}
            {groupKeyFilter && !intersectionOrderIds && (
              <span className="active-dev-chip" style={{ fontSize: 11 }}>
                Group: {groupKeyFilter}
                <button className="active-dev-clear" onClick={clearGroupKey}>✕</button>
              </span>
            )}
          </div>
          {/* Alert button — visible whenever any filter is active and there are orders */}
          {!loading && total > 0 && activeFilterCount > 0 && (
            <button
              className="ac-alert-btn"
              style={{ whiteSpace: 'nowrap', marginLeft: 'auto' }}
              onClick={() => setAlertModal(true)}
            >
              ✉ Send Alert
            </button>
          )}
        </div>

        {loading && orders.length === 0 ? (
          <div className="empty">
            <div className="empty-text">Loading orders…</div>
          </div>
        ) : orders.length === 0 ? (
          <div className="empty">
            <div className="empty-icon">🔍</div>
            <div className="empty-text">No orders match the current filters</div>
            {activeFilterCount > 0 && (
              <button
                className="action-btn"
                style={{ marginTop: 12 }}
                onClick={() => dispatch({ type: 'GOTO_ORDERS' })}
              >
                Clear filters
              </button>
            )}
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
                  <th>Issues</th>
                  <th></th>
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
                        {(o.Deviations || [])
                          .map((d) => DEV_LABELS[d.rule_id || d.type] || d.rule_id || d.type)
                          .filter((v, i, arr) => arr.indexOf(v) === i)
                          .join(', ') || '—'}
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

      {alertModal && (
        <OrdersAlertModal
          filterCtx={{
            orderCount:        total,
            deviationType:     deviationTypeFilter,
            groupKey:          groupKeyFilter,
            statusFilter,
            riskFilter,
            intersectionLabels,
          }}
          onClose={() => setAlertModal(false)}
        />
      )}
    </div>
  );
}
