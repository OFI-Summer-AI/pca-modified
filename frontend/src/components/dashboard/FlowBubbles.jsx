import { useApp } from '../../context/AppContext.jsx';

export default function FlowBubbles({ data }) {
  const { state, dispatch } = useApp();
  const { selectedFlowSteps } = state;

  // Use pre-computed server aggregate — no client-side order iteration needed
  const fb = data.flowBubbles || {};
  const standardFlow = fb.standard_flow || [];
  const criticalSteps = new Set(fb.critical_steps || []);
  const steps = fb.steps || {};

  if (standardFlow.length === 0) return null;

  const isFiltering = selectedFlowSteps.length > 0;
  const toggle = (step) => dispatch({ type: 'TOGGLE_FLOW_STEP', payload: step });
  const clear = () => dispatch({ type: 'CLEAR_FLOW_FILTER' });

  return (
    <div className="table-card">
      <div className="table-top" style={{ flexWrap: 'wrap', gap: 8 }}>
        <span className="section-title">Standard Process Flow</span>
        <div className="flow-filter-meta">
          {!isFiltering && (
            <span className="flow-filter-hint">Click a step to filter orders</span>
          )}
          {isFiltering && (
            <>
              <span className="flow-filter-hint">
                <strong>{selectedFlowSteps.length}</strong> step(s) selected
              </span>
              <div className="flow-filter-actions">
                <button className="flow-clear-btn" onClick={clear}>✕ Clear</button>
              </div>
            </>
          )}
        </div>
      </div>

      {isFiltering && (
        <div className="flow-selected-sequence">
          <span className="fss-label">Filter:</span>
          {selectedFlowSteps.map((step, i) => (
            <span key={step}>
              <span className="fss-pill">{step}</span>
              {i < selectedFlowSteps.length - 1 && <span className="fss-arrow"> → </span>}
            </span>
          ))}
        </div>
      )}

      <div className="flow-bubbles">
        {standardFlow.map((step, idx) => {
          const isCrit = criticalSteps.has(step);
          const isSelected = selectedFlowSteps.includes(step);
          const isDimmed = isFiltering && !isSelected;
          const stepData = steps[step] || {};
          const devCnt = stepData.devCount || 0;
          const passCnt = stepData.passCount || 0;

          return (
            <div key={step} className="flow-bubble-wrap">
              <div
                className={[
                  'flow-bubble',
                  isCrit ? 'critical-step' : '',
                  isSelected ? 'selected' : '',
                  isDimmed ? 'seq-dimmed' : '',
                  isSelected ? 'seq-active' : '',
                ].filter(Boolean).join(' ')}
                onClick={() => toggle(step)}
              >
                <span className="bubble-num">{idx + 1}</span>
                {step}
                {isCrit && <span className="bubble-crit">★</span>}
                {devCnt > 0 && (
                  <span className="flow-bubble-count dev-count-active">⚠ {devCnt}</span>
                )}
                {devCnt === 0 && (
                  <span className="flow-bubble-count pass-count-badge">✓ {passCnt}</span>
                )}
              </div>
              {idx < standardFlow.length - 1 && (
                <span className="flow-bubble-arrow">→</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
