import { AppProvider, useApp } from './context/AppContext.jsx';
import Sidebar from './components/layout/Sidebar.jsx';
import Topbar from './components/layout/Topbar.jsx';
import Toast from './components/common/Toast.jsx';
import AlertModal from './components/modals/AlertModal.jsx';
import ChatPanel from './components/chat/ChatPanel.jsx';
import Upload from './pages/Upload.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Orders from './pages/Orders.jsx';
import OrderDetail from './pages/OrderDetail.jsx';

function AppShell() {
  const { state } = useApp();
  const { currentPage, showAlertModal, appData } = state;

  // Upload/splash page is full-screen — no sidebar or topbar
  const isSplash = currentPage === 'upload' || !appData;

  if (isSplash) {
    return (
      <div className="shell shell-upload">
        <Upload />
        <Toast />
      </div>
    );
  }

  return (
    <div className="shell">
      <Sidebar />
      <div className="main">
        <Topbar />
        {currentPage === 'dashboard' && <Dashboard />}
        {currentPage === 'orders' && <Orders />}
        {currentPage === 'detail' && <OrderDetail />}
      </div>
      {showAlertModal && <AlertModal />}
      <ChatPanel />
      <Toast />
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <AppShell />
    </AppProvider>
  );
}
