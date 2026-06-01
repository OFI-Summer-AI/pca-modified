import { useEffect, useRef, useState } from 'react';
import { useApp } from '../context/AppContext.jsx';
import StatusBadge from '../components/common/StatusBadge.jsx';
import RiskBadge from '../components/common/RiskBadge.jsx';
import PAM_CONFIG from '../config.js';

function buildStandardFlowSteps(order) {
  const standardFlow = order.Standard_Flow || [];
  const actualSet = new Set(order.Actual_Flow || []);
  const criticalSet = new Set(order.Critical_Steps || []);
  return standardFlow.map((step, idx) => ({
    idx, step,
    present: actualSet.has(step),
    isCrit: criticalSet.has(step),
  }));
}

function buildActualFlowSteps(order) {
  const actualFlow = order.Actual_Flow || [];
  const standardSet = new Set(order.Standard_Flow || []);
  const deviations = order.Deviations || [];
  const deviationTypes = new Set(deviations.map((d) => d.type));
  const hasLateApproval = deviationTypes.has('LATE_APPROVAL');
  const hasOutOfSeq = deviationTypes.has('OUT_OF_SEQUENCE');
  const hasWrongSource = deviationTypes.has('DOMAIN_RULE_VIOLATION');
  const hasDelay = deviationTypes.has('DELAYED') || deviationTypes.has('DELAY_FLAG');

  // Build a label for domain rule violations (e.g. "WRONG_SOURCE")
  const ruleLabels = deviations
    .filter((d) => d.type === 'DOMAIN_RULE_VIOLATION' && d.rule_id)
    .map((d) => d.rule_id)
    .join(', ');

  const meta = order.metadata || {};
  const cleanVal = (v) => {
    if (!v) return null;
    const s = String(v).trim();
    return ['none', 'nan', 'null', ''].includes(s.toLowerCase()) ? null : s;
  };
  const optimalSource = cleanVal(meta.OPTIMAL_SOURCE_LOCATION) || cleanVal(meta.optimal_source);

  return actualFlow.map((step, idx) => {
    const inStandard = standardSet.has(step);
    let decision = 'ALLOW';
    let reason = '';

    if (!inStandard && step.includes('change')) {
      decision = 'WARN'; reason = 'Unauthorized change detected';
    } else if (step === 'delete purchase order item') {
      decision = 'BLOCK'; reason = 'PO deletion detected';
    } else if (hasLateApproval && step === 'approve purchase order' && idx > 2) {
      decision = 'ALERT'; reason = 'Late approval detected';
    } else if (hasOutOfSeq && inStandard) {
      const stdIdx = (order.Standard_Flow || []).indexOf(step);
      if (stdIdx > idx) { decision = 'ALERT'; reason = 'Out of expected sequence'; }
    } else if (hasWrongSource) {
      decision = 'WARN';
      reason = optimalSource
        ? `${ruleLabels || 'WRONG_SOURCE'} — correct source is ${optimalSource}`
        : `${ruleLabels || 'WRONG_SOURCE'} — non-compliant source location`;
    } else if (hasDelay) {
      decision = 'ALERT';
      reason = 'Delivery timing deviation';
    }

    return { idx, step, decision, reason };
  });
}

const DECISION_BADGE_CLS = { ALLOW: 'ALLOW', BLOCK: 'BLOCK', ALERT: 'ALERT', WARN: 'WARN' };
const STEP_NUM_CLS = { ALLOW: 'ok', BLOCK: 'err', ALERT: 'warn', WARN: 'warn' };

export default function OrderDetail() {
  const { state, dispatch } = useApp();
  const { sessionId, detailOrderNum, previousPage } = state;

  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [rcaInsights, setRcaInsights] = useState(null);
  const [rcaLoading, setRcaLoading] = useState(false);
  const rcaFetchedFor = useRef(null);

  useEffect(() => {
    if (!detailOrderNum || !sessionId) return;
    setLoading(true);
    setError('');
    setOrder(null);
    setRcaInsights(null);
    rcaFetchedFor.current = null;

    fetch(`${PAM_CONFIG.API_BASE}/orders/${detailOrderNum}?session_id=${sessionId}`)
      .then((r) => {
        if (!r.ok) throw new Error(`Order not found (${r.status})`);
        return r.json();
      })
      .then((data) => { setOrder(data); setLoading(false); })
      .catch((err) => { setError(err.message); setLoading(false); });
  }, [detailOrderNum, sessionId]);

  // Fetch contextual RCA once order is loaded and has deviations
  useEffect(() => {
    if (!order || !sessionId) return;
    if (rcaFetchedFor.current === order.Order_Number) return;
    const deviations = order.Deviations || [];
    if (deviations.length === 0) return;

    rcaFetchedFor.current = order.Order_Number;
    setRcaLoading(true);

    fetch(`${PAM_CONFIG.API_BASE}/rca/contextual`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ order_id: String(order.Order_Number), session_id: sessionId }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.root_cause) setRcaInsights(data);
        setRcaLoading(false);
      })
      .catch(() => setRcaLoading(false));
  }, [order, sessionId]);

  const goBack = () => dispatch({ type: 'SET_PAGE', payload: previousPage || 'orders' });

  if (loading) {
    return (
      <div className="page">
        <button className="back-btn" onClick={goBack}>← Back</button>
        <div className="empty"><div className="empty-text">Loading order…</div></div>
      </div>
    );
  }

  if (error || !order) {
    return (
      <div className="page">
        <button className="back-btn" onClick={goBack}>← Back to Orders</button>
        <div className="empty">
          <div className="empty-icon">🔍</div>
          <div className="empty-text">{error || 'Order not found'}</div>
        </div>
      </div>
    );
  }

  const stdSteps = buildStandardFlowSteps(order);
  const actSteps = buildActualFlowSteps(order);
  const deviations = order.Deviations || [];
  const meta = order.metadata || {};

  // TAT: show only when meaningful (> 0)
  const tatHours = order.TAT_Hours;
  const tatStr = (tatHours != null && tatHours > 0) ? `${Number(tatHours).toFixed(1)} h` : '—';

  // Clean metadata value — treat "None"/"nan"/"null"/"" as absent
  const cleanMeta = (v) => {
    if (!v) return null;
    const s = String(v).trim();
    return ['none', 'nan', 'null', ''].includes(s.toLowerCase()) ? null : s;
  };

  // Order date: prefer actual movement date, fall back to scheduled date
  const orderDate =
    cleanMeta(order.Order_Date) ||
    (cleanMeta(meta.WADAT_IST) ? cleanMeta(meta.WADAT_IST).slice(0, 10) : null) ||
    (cleanMeta(meta.actual_date) ? cleanMeta(meta.actual_date).slice(0, 10) : null) ||
    (cleanMeta(meta.EINDT) ? cleanMeta(meta.EINDT).slice(0, 10) : null) ||
    '—';

  // Scheduled date from metadata
  const scheduledDate =
    (cleanMeta(meta.EINDT) ? cleanMeta(meta.EINDT).slice(0, 10) : null) ||
    (cleanMeta(meta.scheduled_date) ? cleanMeta(meta.scheduled_date).slice(0, 10) : null) ||
    '—';

  return (
    <div className="page">
      <button className="back-btn" onClick={goBack}>← Back to Orders</button>

      {/* Header */}
      <div className="detail-header-card">
        <div>
          <div className="detail-order-label">Order Number</div>
          <div className="detail-order-num">{order.Order_Number}</div>
          {order.Customer && <div className="detail-customer">{order.Customer}</div>}
        </div>
        <div className="detail-header-badges">
          <StatusBadge status={order.Process_Status} large />
          <RiskBadge risk={order.Risk_Level} large />
        </div>
      </div>

      {/* Metrics */}
      <div className="detail-card">
        <div className="detail-card-title">Order Metrics</div>
        <div className="meta-grid">
          <div className="meta-item">
            <div className="meta-key">Activity Steps</div>
            <div className="meta-val">{(order.Actual_Flow || []).length}</div>
          </div>
          <div className="meta-item">
            <div className="meta-key">{(order.Standard_Flow || []).length > 0 ? 'Standard Steps' : 'Compliance Mode'}</div>
            <div className="meta-val" style={{ fontSize: (order.Standard_Flow || []).length === 0 ? '0.75rem' : undefined, color: (order.Standard_Flow || []).length === 0 ? 'var(--text3)' : undefined }}>
              {(order.Standard_Flow || []).length > 0 ? (order.Standard_Flow || []).length : 'Rule-based'}
            </div>
          </div>
          <div className="meta-item">
            <div className="meta-key">Deviations</div>
            <div className="meta-val" style={{ color: deviations.length > 0 ? 'var(--critical)' : 'var(--pass)' }}>
              {deviations.length}
            </div>
          </div>
          <div className="meta-item">
            <div className="meta-key">Risk Score</div>
            <div className="meta-val">{order.Deviation_Score || 0}</div>
          </div>
          <div className="meta-item">
            <div className="meta-key">Actual Date</div>
            <div className="meta-val">{orderDate}</div>
          </div>
          <div className="meta-item">
            <div className="meta-key">Scheduled Date</div>
            <div className="meta-val">{scheduledDate}</div>
          </div>
          {tatStr !== '—' && (
            <div className="meta-item">
              <div className="meta-key">Cycle Time</div>
              <div className="meta-val">{tatStr}</div>
            </div>
          )}
        </div>
      </div>

      {/* Flow comparison */}
      <div className="detail-card">
        <div className="detail-card-title">
          {stdSteps.length > 0 ? 'Process Flow Comparison' : 'Movement & Compliance'}
        </div>
        <div className="flow-compare">
          {stdSteps.length > 0 ? (
            <div>
              <div className="flow-col-title standard">⊞ Standard Flow (Expected)</div>
              <div className="flow-steps">
                {stdSteps.map(({ idx, step, present, isCrit }) => (
                  <div key={idx} className="flow-step">
                    <div className={`step-num ${present ? 'ok' : 'err'}`}>{idx + 1}</div>
                    <div>
                      <div className="step-name">
                        {step}
                        {isCrit && <span className="crit-star"> ★</span>}
                      </div>
                      <div className="step-reason">{present ? '✓ OK' : '✗ MISSING'}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div>
              <div className="flow-col-title standard">⊞ Compliance Checks</div>
              <div className="flow-steps">
                {(() => {
                  const violatedRules = new Set(
                    deviations
                      .filter((d) => d.rule_id)
                      .map((d) => d.rule_id)
                  );
                  const hasDelay = deviations.some((d) => d.type === 'DELAYED');
                  const hasDelayFlag = deviations.some((d) => d.type === 'DELAY_FLAG');

                  const checks = [];

                  // Domain rule violations first
                  deviations
                    .filter((d) => d.type === 'DOMAIN_RULE_VIOLATION')
                    .forEach((d, i) => {
                      checks.push(
                        <div key={`rule-${i}`} className="flow-step">
                          <div className="step-num err">✗</div>
                          <div>
                            <div className="step-name">{d.rule_id || 'Rule Violation'}</div>
                            <div className="step-reason" style={{ color: 'var(--high)' }}>{d.detail}</div>
                          </div>
                        </div>
                      );
                    });

                  if (hasDelay) {
                    checks.push(
                      <div key="delay" className="flow-step">
                        <div className="step-num err">✗</div>
                        <div>
                          <div className="step-name">DELIVERY TIMING</div>
                          <div className="step-reason" style={{ color: 'var(--high)' }}>Actual date later than scheduled</div>
                        </div>
                      </div>
                    );
                  }

                  if (hasDelayFlag) {
                    checks.push(
                      <div key="delayflag" className="flow-step">
                        <div className="step-num warn">!</div>
                        <div>
                          <div className="step-name">DELAY FLAG</div>
                          <div className="step-reason" style={{ color: 'var(--medium)' }}>Delay flag set on this delivery</div>
                        </div>
                      </div>
                    );
                  }

                  if (checks.length === 0) {
                    checks.push(
                      <div key="ok" className="no-dev-msg" style={{ color: 'var(--pass)' }}>
                        ✓ All compliance checks passed
                      </div>
                    );
                  }

                  return checks;
                })()}
              </div>
            </div>
          )}

          <div>
            <div className="flow-col-title actual">⊟ Actual Flow (Observed)</div>
            <div className="flow-steps">
              {actSteps.map(({ idx, step, decision, reason }) => (
                <div key={idx} className="flow-step">
                  <div className={`step-num ${STEP_NUM_CLS[decision] || 'ok'}`}>{idx + 1}</div>
                  <div>
                    <div className="step-name">{step}</div>
                    <span className={`step-badge ${DECISION_BADGE_CLS[decision]}`}>{decision}</span>
                    {reason && <div className="step-reason">{reason}</div>}
                  </div>
                </div>
              ))}
              {actSteps.length === 0 && (
                <div className="no-dev-msg">No activity recorded</div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Deviations */}
      <div className="detail-card">
        <div className="detail-card-title">Detected Deviations</div>
        {deviations.length === 0 ? (
          <div className="no-dev-msg">✓ No deviations detected — process is fully compliant</div>
        ) : (
          <div className="dev-list">
            {deviations.map((d, i) => (
              <div key={i} className={`dev-item ${d.severity}`}>
                <div className="dev-sev">{d.severity}</div>
                <div>
                  <div className="dev-type">{d.rule_id || d.type}</div>
                  {d.rule_id && d.rule_id !== d.type && (
                    <div className="dev-detail" style={{ color: 'var(--text3)', fontSize: 10, marginBottom: 2 }}>
                      {d.type}
                    </div>
                  )}
                  <div className="dev-detail">{d.detail}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* AI Insights */}
      {(deviations.length > 0) && (
        <div className="detail-card">
          <div className="detail-card-title">AI Insights</div>
          <div className="ai-cards">
            <div className="ai-card rc">
              <div className="ai-card-title">🔍 Root Cause</div>
              <div className="ai-card-body">
                {(rcaInsights || order).root_cause || '—'}
              </div>
            </div>
            <div className="ai-card br">
              <div className="ai-card-title">⚡ Business Risk</div>
              <div className="ai-card-body">
                {(rcaInsights || order).business_risk || '—'}
              </div>
            </div>
            <div className="ai-card rm">
              <div className="ai-card-title">✦ Recommendation</div>
              <div className="ai-card-body">
                {(rcaInsights || order).recommendation || '—'}
              </div>
            </div>
          </div>
          {rcaLoading && (
            <div className="exec-summary-loading" style={{ marginTop: 10 }}>
              Generating contextual analysis with order-specific values…
            </div>
          )}
          {rcaInsights && !rcaLoading && (
            <div style={{ marginTop: 8, fontSize: 10, color: 'var(--text3)' }}>
              Contextual AI analysis — specific to this order
            </div>
          )}
        </div>
      )}
    </div>
  );
}
