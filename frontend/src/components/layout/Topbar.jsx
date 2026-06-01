import { useApp } from '../../context/AppContext.jsx';

const PAGE_TITLES = {
  dashboard: { title: 'Compliance Dashboard', sub: 'Deviation monitoring & process analytics' },
  orders: { title: 'Order Register', sub: 'Full order list with filtering & search' },
  detail: { title: 'Order Detail', sub: 'Deviation breakdown & root cause analysis' },
};

export default function Topbar() {
  const { state, dispatch } = useApp();
  const { currentPage, appData, chatOpen, sessionId } = state;

  const info = PAGE_TITLES[currentPage] || PAGE_TITLES.dashboard;
  const hasAlerts = appData && (appData.statusSummary?.BLOCKED || 0) > 0;
  const showChat = currentPage !== 'upload' && sessionId;

  return (
    <header className="topbar">
      <div>
        <div className="topbar-title">{info.title}</div>
        <div className="topbar-sub">{info.sub}</div>
      </div>
      <div className="topbar-right">
        <div className="badge-live">
          <span className="dot-live" />
          Live
        </div>
        {showChat && (
          <button
            className={`chat-toggle-btn${chatOpen ? ' chat-toggle-active' : ''}`}
            onClick={() => dispatch({ type: 'TOGGLE_CHAT' })}
            title="Open compliance assistant"
          >
            💬 Assistant
          </button>
        )}
        {hasAlerts && (
          <button
            className="send-alert-btn"
            onClick={() => dispatch({ type: 'OPEN_ALERT_MODAL' })}
          >
            ⚠ Send High Risk Alerts
          </button>
        )}
      </div>
    </header>
  );
}
