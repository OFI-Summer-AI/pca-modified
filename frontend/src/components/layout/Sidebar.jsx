import { useApp } from '../../context/AppContext.jsx';

export default function Sidebar() {
  const { state, dispatch } = useApp();
  const { currentPage } = state;

  const nav = (page) => dispatch({ type: 'SET_PAGE', payload: page });

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-mark">OFI</div>
        <div className="logo-sub">Process Compliance Agent</div>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section">Analytics</div>
        <div
          className={`nav-item${currentPage === 'dashboard' ? ' active' : ''}`}
          onClick={() => nav('dashboard')}
        >
          <span className="icon">◈</span> Dashboard
        </div>
        <div
          className={`nav-item${currentPage === 'orders' || currentPage === 'detail' ? ' active' : ''}`}
          onClick={() => nav('orders')}
        >
          <span className="icon">◻</span> Orders
        </div>
      </nav>

      <div className="sidebar-bottom">
        <button
          className="upload-btn"
          onClick={() => dispatch({ type: 'SET_PAGE', payload: 'upload' })}
        >
          ⟳ New Analysis
        </button>
      </div>
    </aside>
  );
}
