import { useApp } from '../../context/AppContext.jsx';

export default function SourceLeaderboard({ data }) {
  const { dispatch } = useApp();
  const leaderboard = data.sourceLeaderboard || [];

  if (leaderboard.length === 0) return null;

  const maxCount = leaderboard[0]?.count || 1;
  const totalWrongSource = leaderboard.reduce((s, r) => s + r.count, 0);

  const handleRowClick = (source) => {
    dispatch({ type: 'GOTO_ORDERS', deviationType: 'WRONG_SOURCE', source });
  };

  const handleViewAll = (e) => {
    e.stopPropagation();
    dispatch({ type: 'GOTO_ORDERS', deviationType: 'WRONG_SOURCE' });
  };

  return (
    <div className="table-card lb-card">
      <div className="table-top">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="section-title">Wrong Source — Location Leaderboard</span>
          <span className="section-count">{leaderboard.length} locations</span>
        </div>
        <button className="insight-view-all-btn" onClick={handleViewAll}>
          View all {totalWrongSource.toLocaleString()} wrong-source orders →
        </button>
      </div>

      <div className="lb-body">
        {/* Column headers */}
        <div className="lb-header-row">
          <span className="lb-col-rank">#</span>
          <span className="lb-col-source">Source Used</span>
          <span className="lb-col-bar"></span>
          <span className="lb-col-count">Orders</span>
          <span className="lb-col-pct">% of WS</span>
          <span className="lb-col-correct">Should Be</span>
          <span className="lb-col-action"></span>
        </div>

        {leaderboard.map((item, i) => (
          <div
            key={item.source}
            className="lb-row"
            onClick={() => handleRowClick(item.source)}
            title={`View ${item.count.toLocaleString()} orders from ${item.source}`}
          >
            <span className="lb-col-rank">
              <span className={`lb-rank-badge ${i === 0 ? 'lb-rank-1' : i === 1 ? 'lb-rank-2' : i === 2 ? 'lb-rank-3' : ''}`}>
                {i + 1}
              </span>
            </span>

            <span className="lb-col-source">
              <span className="lb-source-code">{item.source}</span>
            </span>

            <span className="lb-col-bar">
              <div className="lb-bar-track">
                <div
                  className="lb-bar-fill"
                  style={{ width: `${(item.count / maxCount) * 100}%` }}
                />
              </div>
            </span>

            <span className="lb-col-count mono-sm">{item.count.toLocaleString()}</span>

            <span className="lb-col-pct">
              <span className="lb-pct-badge">{item.pct_of_ws}%</span>
            </span>

            <span className="lb-col-correct">
              {item.correct_source ? (
                <span className="lb-correct-code">
                  <span className="lb-arrow">→</span> {item.correct_source}
                </span>
              ) : (
                <span className="lb-no-correct">—</span>
              )}
            </span>

            <span className="lb-col-action">
              <span className="lb-drill">View orders →</span>
            </span>
          </div>
        ))}
      </div>

      <div className="lb-footer">
        <span className="lb-footer-note">
          Click any row to see all orders from that source location · Showing top {leaderboard.length}
        </span>
      </div>
    </div>
  );
}
