import { useApp } from '../../context/AppContext.jsx';

const RANK_CLS = ['r1', 'r2', 'r3', '', ''];

export default function TopSequences({ data }) {
  const { state, dispatch } = useApp();
  const { selectedSequence } = state;

  // Use pre-computed server aggregate — no client-side order iteration needed
  const seqs = (data.topSequences || []).slice(0, 5);
  const total = data.totalOrders || 0;

  if (seqs.length === 0) return null;

  const toggle = (idx) => dispatch({ type: 'TOGGLE_SEQUENCE', payload: idx });

  return (
    <div className="table-card">
      <div className="table-top">
        <span className="section-title">Top Process Sequences</span>
        <span className="section-count">{seqs.length}</span>
      </div>
      <div>
        {seqs.map((seq, idx) => (
          <div
            key={idx}
            className={`seq-item${selectedSequence === idx ? ' seq-selected' : ''}`}
            onClick={() => toggle(idx)}
          >
            <div className={`seq-rank ${RANK_CLS[idx] || ''}`}>{idx + 1}</div>
            <div className="seq-steps">
              {seq.sequence.map((step, si) => (
                <span key={si}>
                  <span className="seq-step-pill">{step}</span>
                  {si < seq.sequence.length - 1 && <span className="seq-arrow">→</span>}
                </span>
              ))}
            </div>
            <div className="seq-meta">
              <div className="seq-count-num">{seq.count}</div>
              <div className="seq-count-lbl">orders</div>
              <div className="seq-pct">{total > 0 ? Math.round((seq.count / total) * 100) : 0}%</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
