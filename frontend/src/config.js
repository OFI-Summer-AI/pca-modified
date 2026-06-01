const PAM_CONFIG = {
  API_BASE: '',          // empty = same origin (Vite proxy handles /analyze, /send-alerts)
  DEMO_MODE: false,
  ALERT_ON_RISK: ['CRITICAL', 'HIGH'],
  ALERT_ON_STATUS: ['BLOCKED'],
  APP_NAME: 'PAM',
  APP_SUBTITLE: 'Process Compliance Agent',
  ORG_NAME: 'OFI Services',
  PROGRESS_STEPS: [
    'Parsing event log…',
    'Grouping orders by ID…',
    'Running AI process definition…',
    'Detecting deviations…',
    'Running AI root cause analysis…',
    'Formatting final output…',
  ],
};

export default PAM_CONFIG;
