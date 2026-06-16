import { useEffect, useState } from 'react';
import { useApp } from '../context/AppContext.jsx';
import PAM_CONFIG from '../config.js';

const DEV_LABELS = {
  WRONG_SOURCE:          'Wrong Source',
  PLANT_MISMATCH:        'Plant Mismatch',
  DELAYED:               'Past Due',
  DELAY_FLAG:            'Pre-Flagged',
  MISSING_CRITICAL_STEP: 'Missing Step',
  OUT_OF_SEQUENCE:       'Out of Sequence',
  DUPLICATE_STEP:        'Duplicate Step',
};

const DEV_DESCRIPTIONS = {
  WRONG_SOURCE:          'Orders dispatched from a non-optimal source location',
  PLANT_MISMATCH:        'Orders processed at a different plant than required',
  DELAYED:               'Orders that arrived after their scheduled delivery date',
  DELAY_FLAG:            'Orders pre-flagged by the source system as delayed',
  MISSING_CRITICAL_STEP: 'Orders where a mandatory process step was not executed',
  OUT_OF_SEQUENCE:       'Orders where process steps occurred in the wrong order',
  DUPLICATE_STEP:        'Orders where the same step was executed multiple times',
};

const GROUP_COL_LABEL = {
  WRONG_SOURCE:          'Source Route',
  PLANT_MISMATCH:        'Plant Route',
  DELAYED:               'Delay Range',
  DELAY_FLAG:            'Category',
  MISSING_CRITICAL_STEP: 'Missing Step',
  OUT_OF_SEQUENCE:       'Sequence',
  DUPLICATE_STEP:        'Duplicated Step',
};

// ── Email Preview Modal ───────────────────────────────────────────────────────
function EmailModal({ modal, onClose }) {
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState(null);
  const [sending, setSending] = useState(false);
  const [status,  setStatus]  = useState(null); // 'sent'|'copied'|'no_smtp'|'error'
  const { state } = useApp();

  useEffect(() => {
    if (!modal) return;
    setLoading(true);
    setStatus(null);
    setPreview(null);
    const p = new URLSearchParams({
      session_id:     state.sessionId,
      deviation_type: modal.deviationType,
      group_key:      modal.group.key,
      group_count:    String(modal.group.count),
      group_pct:      String(modal.group.pct),
    });
    fetch(`${PAM_CONFIG.API_BASE}/compliance/email-preview?${p}`)
      .then((r) => r.json())
      .then((d) => { setPreview(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [modal]);

  const handleSend = async () => {
    setSending(true);
    setStatus(null);
    try {
      const res  = await fetch(`${PAM_CONFIG.API_BASE}/compliance/send-group-alert`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id:     state.sessionId,
          deviation_type: modal.deviationType,
          group_key:      modal.group.key,
          group_data:     modal.group,
        }),
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

  const handleCopy = () => {
    if (!preview) return;
    navigator.clipboard.writeText(`Subject: ${preview.subject}\n\n${preview.body || ''}`);
    setStatus('copied');
  };

  return (
    <div className="email-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="email-modal email-modal-wide">
        <div className="email-modal-hdr">
          <span className="email-modal-title">Email Alert Preview</span>
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
            {/* Render the OFI-branded HTML email in a sandboxed iframe */}
            <div className="email-body-wrap">
              {preview.html_body ? (
                <iframe
                  srcDoc={preview.html_body}
                  title="Email Preview"
                  style={{ width: '100%', height: '460px', border: 'none', borderRadius: '4px' }}
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
            {status === 'copied'  && <span className="email-ok">✓ Copied to clipboard</span>}
            {status === 'no_smtp' && <span className="email-warn">SMTP not configured — copy the template to send manually</span>}
            {status === 'error'   && <span className="email-err">Send failed — check SMTP settings in .env</span>}
          </div>
          <div className="email-modal-btns">
            <button className="email-copy-btn" onClick={handleCopy} disabled={!preview}>
              Copy Plain Text
            </button>
            <button
              className="email-send-btn"
              onClick={handleSend}
              disabled={sending || !preview || status === 'sent'}
            >
              {sending ? 'Sending…' : 'Send Email'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Section for one deviation type ────────────────────────────────────────────
const MIN_ORDERS = 5;

function ComplianceSection({ section, dispatch, onAlertClick, activeFilters, onFilterToggle }) {
  const { deviation_type, total_orders, groups } = section;
  const [expanded,  setExpanded]  = useState(false);
  const [showSmall, setShowSmall] = useState(false);

  const significant = showSmall ? groups : groups.filter((g) => g.count >= MIN_ORDERS);
  const smallCount  = groups.length - significant.length;
  const visible     = expanded ? significant : significant.slice(0, 8);
  const hasMore     = significant.length > 8;

  const isActive = (group) =>
    activeFilters.some((f) => f.type === deviation_type && f.key === group.key);

  return (
    <div className="ac-section">
      <div className="ac-section-hdr">
        <div className="ac-section-hdr-left">
          <span className="ac-section-title">{DEV_LABELS[deviation_type] || deviation_type}</span>
          <span className="ac-section-count">{total_orders.toLocaleString()} orders</span>
          <span className="ac-section-desc">{DEV_DESCRIPTIONS[deviation_type]}</span>
        </div>
        <button
          className="insight-view-all-btn"
          onClick={() => dispatch({ type: 'GOTO_ORDERS', deviationType: deviation_type })}
        >
          View all →
        </button>
      </div>

      {significant.length === 0 ? (
        <div className="ac-no-groups">No significant groups found</div>
      ) : (
        <>
          <div className="ac-group-table">
            <div className="ac-group-row ac-group-row-hdr">
              <span className="ac-col-rank">#</span>
              <span className="ac-col-name">{GROUP_COL_LABEL[deviation_type] || 'Group'}</span>
              <span className="ac-col-bar" />
              <span className="ac-col-count">Orders</span>
              <span className="ac-col-share">Share</span>
              <span className="ac-col-actions">Actions</span>
            </div>

            {visible.map((group, i) => {
              const active = isActive(group);
              return (
                <div
                  key={group.key}
                  className={`ac-group-row${active ? ' ac-group-row-active' : ''}`}
                >
                  <span className="ac-col-rank">
                    <span className={`ac-rank-badge${i < 3 ? ` ac-rank-${i + 1}` : ''}`}>
                      {i + 1}
                    </span>
                  </span>

                  <span className="ac-col-name" style={{ gap: 8, display: 'flex', alignItems: 'center' }}>
                    <button
                      className={`ac-filter-toggle${active ? ' ac-filter-toggle-on' : ''}`}
                      onClick={() => onFilterToggle(deviation_type, group)}
                      title={active ? 'Remove from cross-filter' : 'Add to cross-filter analysis'}
                    >
                      {active ? '✓' : '+'}
                    </button>
                    <span className="ac-group-key">{group.key}</span>
                  </span>

                  <span className="ac-col-bar">
                    <div className="ac-bar-track">
                      <div className="ac-bar-fill" style={{ width: `${Math.max(group.pct, 0.5)}%` }} />
                    </div>
                  </span>

                  <span className="ac-col-count mono-sm">{group.count.toLocaleString()}</span>

                  <span className="ac-col-share ac-pct-badge">
                    {group.pct_display || `${group.pct}%`}
                  </span>

                  <span className="ac-col-actions">
                    <button
                      className="ac-view-btn"
                      onClick={() => dispatch({ type: 'GOTO_ORDERS', deviationType: deviation_type, groupKey: group.key })}
                    >
                      View
                    </button>
                    <button className="ac-alert-btn" onClick={() => onAlertClick(group)}>
                      ✉ Alert
                    </button>
                  </span>
                </div>
              );
            })}
          </div>

          <div className="ac-section-footer">
            {hasMore && (
              <button className="ac-show-more" onClick={() => setExpanded((e) => !e)}>
                {expanded ? 'Show fewer' : `Show ${significant.length - 8} more`}
              </button>
            )}
            {smallCount > 0 && (
              <button className="ac-show-small" onClick={() => setShowSmall((s) => !s)}>
                {showSmall
                  ? 'Hide minor groups'
                  : `+ ${smallCount} minor group${smallCount > 1 ? 's' : ''} (< ${MIN_ORDERS} orders)`}
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Compliance() {
  const { state, dispatch } = useApp();
  const { sessionId, appData } = state;

  const devTypeCounts = appData?.deviationTypeCounts || {};
  const available     = Object.keys(devTypeCounts);

  // Deviation-type pills (which sections to show)
  const [selected,    setSelected]    = useState(() => [...available]);
  const [breakdown,   setBreakdown]   = useState(null);
  const [loading,     setLoading]     = useState(false);
  const [emailModal,  setEmailModal]  = useState(null); // { group, deviationType }

  // Cross-filter state — groups the user has "pinned" for intersection analysis
  const [activeFilters, setActiveFilters] = useState([]); // [{type, key, label, count}]
  const [intersection,  setIntersection]  = useState(null);
  const [intersecting,  setIntersecting]  = useState(false);

  // Stable sorted keys — no mutation
  const availableKey = [...available].sort().join(',');
  const selectionKey = [...selected].sort().join(',');
  const filterKey    = [...activeFilters]
    .map((f) => `${f.type}:${f.key}`)
    .sort()
    .join('|');

  // Sync type pills when a new analysis runs
  useEffect(() => {
    if (availableKey) setSelected([...available]);
    setActiveFilters([]);
    setIntersection(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [availableKey]);

  // Fetch section breakdown
  useEffect(() => {
    if (!sessionId || !selectionKey) { setBreakdown(null); return; }
    const controller = new AbortController();
    setLoading(true);
    setBreakdown(null);
    const params = new URLSearchParams({ session_id: sessionId });
    selectionKey.split(',').forEach((t) => params.append('deviation_types', t));
    fetch(`${PAM_CONFIG.API_BASE}/compliance/breakdown?${params}`, { signal: controller.signal })
      .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then((data) => { setBreakdown(data.sections || []); setLoading(false); })
      .catch((err) => { if (err.name !== 'AbortError') { setBreakdown([]); setLoading(false); } });
    return () => controller.abort();
  }, [sessionId, selectionKey]);

  // Fetch intersection count whenever 2+ cross-filters are active
  useEffect(() => {
    if (activeFilters.length < 2) { setIntersection(null); return; }
    const controller = new AbortController();
    setIntersecting(true);
    const params = new URLSearchParams({ session_id: sessionId });
    activeFilters.forEach((f) => params.append('filters', `${f.type}:${f.key}`));
    fetch(`${PAM_CONFIG.API_BASE}/compliance/intersect?${params}`, { signal: controller.signal })
      .then((r) => r.json())
      .then((data) => { setIntersection(data); setIntersecting(false); })
      .catch((err) => { if (err.name !== 'AbortError') setIntersecting(false); });
    return () => controller.abort();
  }, [sessionId, filterKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleType = (type) => {
    setSelected((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
  };

  const toggleGroupFilter = (type, group) => {
    setActiveFilters((prev) => {
      const exists = prev.some((f) => f.type === type && f.key === group.key);
      if (exists) return prev.filter((f) => !(f.type === type && f.key === group.key));
      return [...prev, {
        type,
        key: group.key,
        label: `${DEV_LABELS[type] || type}: ${group.key}`,
        count: group.count,
      }];
    });
    setIntersection(null);
  };

  const clearFilters = () => { setActiveFilters([]); setIntersection(null); };

  const allSelected = selected.length === available.length;

  if (!appData) return null;

  // Unique deviation types across active filters (for meaningful cross-type query)
  const filterTypes = [...new Set(activeFilters.map((f) => f.type))];

  return (
    <div className="page">
      {/* Page header */}
      <div className="ac-page-hdr">
        <div>
          <h2 className="ac-page-title">Action Center</h2>
          <p className="ac-page-sub">
            Segmented compliance analysis · click <strong>+</strong> on any group to build a cross-filter · send targeted alerts in one click
          </p>
        </div>
      </div>

      {/* Issue-type pills */}
      <div className="ac-filter-bar">
        <span className="ac-filter-label">Issue Types</span>
        <div className="ac-pills-wrap">
          {available.map((type) => (
            <button
              key={type}
              className={`ac-pill${selected.includes(type) ? ' ac-pill-on' : ''}`}
              onClick={() => toggleType(type)}
            >
              {DEV_LABELS[type] || type}
              <span className="ac-pill-count">{(devTypeCounts[type] || 0).toLocaleString()}</span>
            </button>
          ))}
          {available.length > 1 && (
            <button
              className="ac-pill-toggle-all"
              onClick={() => setSelected(allSelected ? [] : [...available])}
            >
              {allSelected ? 'Deselect All' : 'Select All'}
            </button>
          )}
        </div>
      </div>

      {/* Cross-filter panel — shown when any group is pinned */}
      {activeFilters.length > 0 && (
        <div className="ac-xfilter-bar">
          <div className="ac-xfilter-top">
            <span className="ac-xfilter-label">Cross-Filter</span>
            <div className="ac-xfilter-chips">
              {activeFilters.map((f) => (
                <span key={`${f.type}:${f.key}`} className="ac-xfilter-chip">
                  <span className="ac-xfilter-chip-type">{DEV_LABELS[f.type] || f.type}</span>
                  <span className="ac-xfilter-chip-key">{f.key}</span>
                  <span className="ac-xfilter-chip-n">{f.count.toLocaleString()}</span>
                  <button
                    className="ac-xfilter-chip-x"
                    onClick={() => toggleGroupFilter(f.type, { key: f.key, count: f.count })}
                  >×</button>
                </span>
              ))}
            </div>
            <button className="ac-xfilter-clear" onClick={clearFilters}>Clear all</button>
          </div>

          <div className="ac-xfilter-result">
            {activeFilters.length < 2 ? (
              <span className="ac-xfilter-hint">
                Pin one more group (from any section below) to find orders with BOTH issues
              </span>
            ) : filterTypes.length < 2 ? (
              <span className="ac-xfilter-hint">
                Select groups from different issue types to find overlap
              </span>
            ) : intersecting ? (
              <span className="ac-xfilter-hint">Finding overlap…</span>
            ) : intersection ? (
              <div className="ac-intersection-result">
                <span className="ac-intersection-count">
                  {intersection.count.toLocaleString()}
                </span>
                <span className="ac-intersection-label">
                  orders have ALL {activeFilters.length} selected issues simultaneously
                </span>
                {intersection.count > 0 && (
                  <button
                    className="ac-intersection-view"
                    onClick={() => dispatch({
                      type: 'GOTO_ORDERS',
                      orderIds: intersection.ids,
                      intersectionLabels: activeFilters.map((f) => `${f.type}:${f.key}`),
                    })}
                  >
                    View orders →
                  </button>
                )}
              </div>
            ) : null}
          </div>
        </div>
      )}

      {/* Section content */}
      {selected.length === 0 ? (
        <div className="ac-empty-state">
          <div className="ac-empty-icon">◈</div>
          <div className="ac-empty-text">Select at least one issue type above to see the breakdown</div>
        </div>
      ) : loading ? (
        <div className="ac-loading-state">
          <div className="ac-loading-text">
            Analysing {selected.length} deviation type{selected.length > 1 ? 's' : ''}…
          </div>
        </div>
      ) : breakdown && breakdown.length > 0 ? (
        <div className="ac-sections">
          {breakdown.map((section) => (
            <ComplianceSection
              key={section.deviation_type}
              section={section}
              dispatch={dispatch}
              activeFilters={activeFilters}
              onFilterToggle={toggleGroupFilter}
              onAlertClick={(group) =>
                setEmailModal({ group, deviationType: section.deviation_type })
              }
            />
          ))}
        </div>
      ) : (
        <div className="ac-empty-state">
          <div className="ac-empty-icon">✓</div>
          <div className="ac-empty-text">No orders found for the selected issue types</div>
        </div>
      )}

      {emailModal && (
        <EmailModal modal={emailModal} onClose={() => setEmailModal(null)} />
      )}
    </div>
  );
}
