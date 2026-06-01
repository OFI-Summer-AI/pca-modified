import { createContext, useContext, useReducer } from 'react';

const AppContext = createContext(null);

const initialState = {
  appData: null,
  rcaLoading: false,
  currentPage: 'upload',
  detailOrderNum: null,
  statusFilter: 'ALL',
  riskFilter: null,
  dateFrom: '',
  dateTo: '',
  searchQuery: '',
  selectedFlowSteps: [],
  selectedSequence: null,
  selectedHeatmapRisk: null,
  previousPage: 'dashboard',
  fileA: null,
  fileB: null,
  toast: null,
  showAlertModal: false,
  // Chat state
  chatOpen: false,
  chatHistory: [],
  sessionId: null,
  // Executive summary
  execSummary: null,
  execSummaryLoading: false,
  // Cluster insights
  clusterInsights: null,
  clusterInsightsLoading: false,
};

function reducer(state, action) {
  switch (action.type) {
    case 'SET_APP_DATA':
      return {
        ...state,
        appData: action.payload,
        currentPage: 'dashboard',
        rcaLoading: false,
        execSummary: null,
        execSummaryLoading: false,
        clusterInsights: null,
        clusterInsightsLoading: false,
        chatHistory: [],
        sessionId: action.sessionId || null,
      };
    case 'SET_RCA_LOADING':
      return { ...state, rcaLoading: action.payload };
    case 'MERGE_RCA': {
      // RCA is now rule-based on the backend — no client-side merge needed.
      // This case is kept for backwards compatibility only.
      return { ...state, rcaLoading: false };
    }
    case 'SET_PAGE':
      return { ...state, currentPage: action.payload, detailOrderNum: null };
    case 'SHOW_DETAIL':
      return { ...state, previousPage: state.currentPage, currentPage: 'detail', detailOrderNum: action.payload };
    case 'SET_STATUS_FILTER':
      return { ...state, statusFilter: action.payload };
    case 'SET_RISK_FILTER':
      return { ...state, riskFilter: state.riskFilter === action.payload ? null : action.payload };
    case 'SET_DATE':
      return { ...state, [action.field]: action.payload };
    case 'CLEAR_DATE':
      return { ...state, dateFrom: '', dateTo: '' };
    case 'SET_SEARCH':
      return { ...state, searchQuery: action.payload };
    case 'TOGGLE_FLOW_STEP': {
      const step = action.payload;
      const steps = state.selectedFlowSteps.includes(step)
        ? state.selectedFlowSteps.filter((s) => s !== step)
        : [...state.selectedFlowSteps, step];
      return { ...state, selectedFlowSteps: steps, selectedSequence: null };
    }
    case 'CLEAR_FLOW_FILTER':
      return { ...state, selectedFlowSteps: [], selectedSequence: null };
    case 'TOGGLE_SEQUENCE':
      return {
        ...state,
        selectedSequence: state.selectedSequence === action.payload ? null : action.payload,
        selectedFlowSteps: [],
      };
    case 'TOGGLE_HEATMAP_RISK':
      return {
        ...state,
        selectedHeatmapRisk: state.selectedHeatmapRisk === action.payload ? null : action.payload,
      };
    case 'SET_FILE':
      return { ...state, [action.field]: action.payload };
    case 'SHOW_TOAST':
      return { ...state, toast: { message: action.message, toastType: action.toastType || 'success' } };
    case 'HIDE_TOAST':
      return { ...state, toast: null };
    case 'OPEN_ALERT_MODAL':
      return { ...state, showAlertModal: true };
    case 'CLOSE_ALERT_MODAL':
      return { ...state, showAlertModal: false };
    // Chat actions
    case 'TOGGLE_CHAT':
      return { ...state, chatOpen: !state.chatOpen };
    case 'OPEN_CHAT':
      return { ...state, chatOpen: true };
    case 'CLOSE_CHAT':
      return { ...state, chatOpen: false };
    case 'ADD_CHAT_MESSAGE':
      return { ...state, chatHistory: [...state.chatHistory, action.payload] };
    case 'UPDATE_LAST_CHAT_MESSAGE': {
      const updated = [...state.chatHistory];
      if (updated.length > 0) {
        updated[updated.length - 1] = { ...updated[updated.length - 1], ...action.payload };
      }
      return { ...state, chatHistory: updated };
    }
    // Streaming: append a token chunk to the last AI message
    case 'APPEND_CHAT_CHUNK': {
      const updated = [...state.chatHistory];
      if (updated.length > 0) {
        const last = updated[updated.length - 1];
        updated[updated.length - 1] = { ...last, content: (last.content || '') + action.payload, loading: false };
      }
      return { ...state, chatHistory: updated };
    }
    // Streaming: attach table data to last AI message
    case 'SET_CHAT_TABLE': {
      const updated = [...state.chatHistory];
      if (updated.length > 0) {
        updated[updated.length - 1] = { ...updated[updated.length - 1], data: action.payload };
      }
      return { ...state, chatHistory: updated };
    }
    case 'CLEAR_CHAT':
      return { ...state, chatHistory: [] };
    // Executive summary
    case 'SET_EXEC_SUMMARY_LOADING':
      return { ...state, execSummaryLoading: action.payload };
    case 'SET_EXEC_SUMMARY':
      return { ...state, execSummary: action.payload, execSummaryLoading: false };
    // Cluster insights
    case 'SET_CLUSTER_INSIGHTS_LOADING':
      return { ...state, clusterInsightsLoading: action.payload };
    case 'SET_CLUSTER_INSIGHTS':
      return { ...state, clusterInsights: action.payload, clusterInsightsLoading: false };
    default:
      return state;
  }
}

export function AppProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  return (
    <AppContext.Provider value={{ state, dispatch }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  return useContext(AppContext);
}
