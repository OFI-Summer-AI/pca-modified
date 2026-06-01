import { useEffect } from 'react';
import { useApp } from '../../context/AppContext.jsx';

export default function Toast() {
  const { state, dispatch } = useApp();
  const { toast } = state;

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => dispatch({ type: 'HIDE_TOAST' }), 3500);
    return () => clearTimeout(t);
  }, [toast, dispatch]);

  if (!toast) return null;

  return (
    <div className={`toast ${toast.toastType}`}>
      {toast.message}
    </div>
  );
}
