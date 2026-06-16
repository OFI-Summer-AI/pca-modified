import { useApp } from '../context/AppContext.jsx';
import KpiRow from '../components/dashboard/KpiRow.jsx';
import StatusCards from '../components/dashboard/StatusCards.jsx';
import ChartsRow from '../components/dashboard/ChartsRow.jsx';
import FlowBubbles from '../components/dashboard/FlowBubbles.jsx';
import TopSequences from '../components/dashboard/TopSequences.jsx';
import InsightsTable from '../components/dashboard/InsightsTable.jsx';
import SourceLeaderboard from '../components/dashboard/SourceLeaderboard.jsx';

function ExecSummaryBanner() {
  const { state } = useApp();
  const { execSummary, execSummaryLoading } = state;
  if (!execSummaryLoading && !execSummary) return null;
  return (
    <div className="exec-summary-banner">
      <div className="exec-summary-label">AI Executive Summary</div>
      {execSummaryLoading
        ? <div className="exec-summary-loading">Generating executive summary…</div>
        : <div className="exec-summary-text">{execSummary}</div>}
    </div>
  );
}

function ClusterInsightsBanner() {
  const { state } = useApp();
  const { clusterInsights, clusterInsightsLoading } = state;
  if (!clusterInsightsLoading && (!clusterInsights || clusterInsights.length === 0)) return null;
  return (
    <div className="exec-summary-banner" style={{ marginTop: 0 }}>
      <div className="exec-summary-label">AI Pattern Analysis</div>
      {clusterInsightsLoading ? (
        <div className="exec-summary-loading">Identifying compliance patterns…</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {clusterInsights.map((insight, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent2)', minWidth: 16, marginTop: 1 }}>
                {i + 1}.
              </span>
              <span className="exec-summary-text" style={{ margin: 0 }}>{insight}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const { state, dispatch } = useApp();
  const { appData, chatOpen } = state;

  if (!appData) return null;

  const displayOrders = appData.insights || [];
  const insightLabel  = 'Top Risk Orders';
  const insightAction = (
    <button
      className="insight-view-all-btn"
      onClick={() => dispatch({ type: 'GOTO_ORDERS', status: 'BLOCKED' })}
    >
      View all in Orders →
    </button>
  );

  return (
    <div className={`page${chatOpen ? ' page-chat-open' : ''}`}>
      <ExecSummaryBanner />
      <ClusterInsightsBanner />
      <KpiRow data={appData} />
      <ChartsRow data={appData} />
      <StatusCards data={appData} />
      {/* Only show 2-col layout when FlowBubbles has actual standard-flow data */}
      {(appData.flowBubbles?.standard_flow || []).length > 0 ? (
        <div className="dash-row-2">
          <TopSequences data={appData} />
          <FlowBubbles data={appData} />
        </div>
      ) : (
        <TopSequences data={appData} />
      )}
      <SourceLeaderboard data={appData} />
      <InsightsTable orders={displayOrders} label={insightLabel} action={insightAction} />
    </div>
  );
}
