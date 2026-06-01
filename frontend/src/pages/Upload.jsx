import { useEffect, useRef, useState } from 'react';
import { useApp } from '../context/AppContext.jsx';
import PAM_CONFIG from '../config.js';

// ── Pipeline steps ────────────────────────────────────────────────────────────
const STEPS = [
  { label: 'Schema Detection',  detail: 'AI scanning column structure · deriving activity template', weight: 5  },
  { label: 'Order Grouping',    detail: 'DuckDB partitioning rows into delivery groups',             weight: 28 },
  { label: 'Frequency Mapping', detail: 'Counting step patterns across all orders',                  weight: 10 },
  { label: 'Flow Inference',    detail: 'AI resolving standard compliance sequence',                 weight: 5  },
  { label: 'Deviation Engine',  detail: 'Parallel compliance checks · scoring risk',                 weight: 17 },
  { label: 'RCA & Formatting',  detail: 'Enriching insights · building analysis output',             weight: 35 },
];
const TOTAL_WEIGHT = STEPS.reduce((s, p) => s + p.weight, 0);

// ── Particle canvas ───────────────────────────────────────────────────────────
function ParticleCanvas({ analyzing }) {
  const canvasRef = useRef(null);
  const stateRef  = useRef({ mouse: { x: -9999, y: -9999 }, analyzing: false, raf: null });

  useEffect(() => { stateRef.current.analyzing = analyzing; }, [analyzing]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx    = canvas.getContext('2d');

    const resize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; };
    resize();
    window.addEventListener('resize', resize);

    // ── 110 particles with home velocity ─────────────────────
    const COUNT  = 110;
    const COLORS = ['#CCA23E', '#d4aa45', '#e6c04a', '#B8860B', '#f0d870', '#a07820'];

    const W0 = canvas.width  || window.innerWidth;
    const H0 = canvas.height || window.innerHeight;

    const particles = Array.from({ length: COUNT }, () => {
      const angle = Math.random() * Math.PI * 2;
      const speed = Math.random() * 0.18 + 0.03;
      const hvx   = Math.cos(angle) * speed;
      const hvy   = Math.sin(angle) * speed;
      return {
        x:    Math.random() * W0,
        y:    Math.random() * H0,
        vx:   hvx, vy: hvy,
        homeVx: hvx, homeVy: hvy,
        size:  Math.random() * 1.6 + 0.4,
        color: COLORS[Math.floor(Math.random() * COLORS.length)],
        alpha: Math.random() * 0.45 + 0.12,
        phase: Math.random() * Math.PI * 2,
        pulseSpeed: Math.random() * 0.010 + 0.005,
      };
    });

    const onMove  = (e) => { stateRef.current.mouse = { x: e.clientX, y: e.clientY }; };
    const onLeave = () =>  { stateRef.current.mouse = { x: -9999, y: -9999 }; };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseleave', onLeave);

    // ── animation loop ────────────────────────────────────────
    const ATTRACT  = 180;   // attraction radius
    const CONNECT  = 110;   // max connection distance
    const REPULSE  = 28;    // minimum separation — soft push when too close
    const DAMPING  = 0.90;  // velocity damping per frame
    const HOME_K   = 0.015; // spring-back to home velocity
    const MAX_CONN = 4;     // max connection lines drawn per particle (prevents dense clusters)

    const draw = () => {
      stateRef.current.raf = requestAnimationFrame(draw);
      const { mouse, analyzing: isAnalyzing } = stateRef.current;
      const W = canvas.width;
      const H = canvas.height;
      const hasMouse = mouse.x > -1000;

      ctx.clearRect(0, 0, W, H);

      // ── update positions ──────────────────────────────────────
      particles.forEach((p) => {
        p.phase += p.pulseSpeed;
        const pulse = isAnalyzing ? 0.5 + 0.5 * Math.abs(Math.sin(p.phase)) : 1;
        p._pulse = pulse;

        // Attraction toward cursor
        if (hasMouse) {
          const dx = mouse.x - p.x;
          const dy = mouse.y - p.y;
          const d  = Math.sqrt(dx * dx + dy * dy);
          if (d < ATTRACT && d > 1) {
            const force = ((ATTRACT - d) / ATTRACT) * 0.45;
            p.vx += (dx / d) * force;
            p.vy += (dy / d) * force;
          }
        }

        // Damping + spring back toward home velocity
        p.vx = p.vx * DAMPING + p.homeVx * HOME_K;
        p.vy = p.vy * DAMPING + p.homeVy * HOME_K;

        p.x += p.vx;
        p.y += p.vy;

        // Wrap
        if (p.x < -10) p.x = W + 10;
        if (p.x > W + 10) p.x = -10;
        if (p.y < -10) p.y = H + 10;
        if (p.y > H + 10) p.y = -10;
      });

      // ── connection lines (limited per particle) ───────────────
      const connCount = new Int8Array(particles.length);
      for (let i = 0; i < particles.length; i++) {
        if (connCount[i] >= MAX_CONN) continue;
        for (let j = i + 1; j < particles.length; j++) {
          if (connCount[j] >= MAX_CONN) continue;
          const a = particles[i], b = particles[j];
          const ddx = a.x - b.x, ddy = a.y - b.y;
          const dd  = Math.sqrt(ddx * ddx + ddy * ddy);
          if (dd < CONNECT && dd > REPULSE) {
            // Soft repulsion — nudge apart when too close, smooths out clusters
            if (dd < REPULSE * 2) {
              const push = (REPULSE * 2 - dd) / (REPULSE * 2) * 0.08;
              const nx = ddx / dd, ny = ddy / dd;
              a.vx += nx * push; a.vy += ny * push;
              b.vx -= nx * push; b.vy -= ny * push;
            }
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.strokeStyle = '#CCA23E';
            ctx.globalAlpha = (1 - dd / CONNECT) * (isAnalyzing ? 0.18 : 0.07);
            ctx.lineWidth   = 0.5;
            ctx.stroke();
            connCount[i]++;
            connCount[j]++;
          }
        }
      }

      // ── draw dots (after lines so dots appear on top) ─────────
      particles.forEach((p) => {
        const pulse = p._pulse ?? 1;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size * pulse, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.globalAlpha = p.alpha * pulse;
        ctx.fill();
      });

      // ── cursor glow ───────────────────────────────────────────
      if (hasMouse) {
        const g = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, ATTRACT);
        g.addColorStop(0,   'rgba(204,162,62,0.10)');
        g.addColorStop(0.4, 'rgba(204,162,62,0.04)');
        g.addColorStop(1,   'rgba(204,162,62,0)');
        ctx.globalAlpha = 1;
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(mouse.x, mouse.y, ATTRACT, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.globalAlpha = 1;
    };

    draw();
    return () => {
      cancelAnimationFrame(stateRef.current.raf);
      window.removeEventListener('resize', resize);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseleave', onLeave);
    };
  }, []);

  return <canvas ref={canvasRef} style={{ position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0 }} />;
}

// ── Pipeline step list ────────────────────────────────────────────────────────
function PipelineProgress({ progress }) {
  const cumulative = STEPS.reduce((acc, s, i) => {
    acc.push((acc[i - 1] || 0) + (s.weight / TOTAL_WEIGHT) * 100);
    return acc;
  }, []);

  return (
    <div className="pipeline-steps">
      {STEPS.map((s, i) => {
        const stepStart = i === 0 ? 0 : cumulative[i - 1];
        const stepEnd   = cumulative[i];
        const done      = progress >= stepEnd;
        const active    = !done && progress >= stepStart;
        const stepPct   = active
          ? Math.round(((progress - stepStart) / (stepEnd - stepStart)) * 100)
          : 0;

        return (
          <div key={s.label} className={`pstep ${done ? 'done' : active ? 'active' : 'pending'}`}>
            <div className="pstep-icon">
              {done   ? '✓'
               : active ? <span className="pstep-spinner" />
               : <span className="pstep-dot" />}
            </div>
            <div className="pstep-body">
              <div className="pstep-label">{s.label}</div>
              {active && <div className="pstep-detail">{s.detail}</div>}
              {active && (
                <div className="pstep-bar-track">
                  <div className="pstep-bar-fill" style={{ width: `${stepPct}%` }} />
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Background vignette ───────────────────────────────────────────────────────
function Vignette() {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none',
      background: 'radial-gradient(ellipse at 50% 50%, transparent 25%, rgba(10,9,8,0.78) 100%)',
    }} />
  );
}

// ── Background helpers ────────────────────────────────────────────────────────
function runSummaryInBackground(sessionId, dispatch) {
  if (!sessionId) return;
  dispatch({ type: 'SET_EXEC_SUMMARY_LOADING', payload: true });
  fetch(`${PAM_CONFIG.API_BASE}/summary`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  })
    .then((r) => r.json())
    .then((d) => dispatch({ type: 'SET_EXEC_SUMMARY', payload: d.narrative || '' }))
    .catch(() => dispatch({ type: 'SET_EXEC_SUMMARY_LOADING', payload: false }));
}

function runClusterInsightsInBackground(sessionId, dispatch) {
  if (!sessionId) return;
  dispatch({ type: 'SET_CLUSTER_INSIGHTS_LOADING', payload: true });
  fetch(`${PAM_CONFIG.API_BASE}/insights/clusters`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  })
    .then((r) => r.json())
    .then((d) => dispatch({ type: 'SET_CLUSTER_INSIGHTS', payload: d.insights || [] }))
    .catch(() => dispatch({ type: 'SET_CLUSTER_INSIGHTS_LOADING', payload: false }));
}

// ── Elapsed time display ──────────────────────────────────────────────────────
function useElapsed(running) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(null);

  useEffect(() => {
    if (running) {
      startRef.current = Date.now();
      const id = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
      }, 1000);
      return () => clearInterval(id);
    } else {
      setElapsed(0);
    }
  }, [running]);

  return elapsed;
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Upload() {
  const { dispatch } = useApp();
  const [status,       setStatus]       = useState('idle');
  const [progress,     setProgress]     = useState(0);
  const [error,        setError]        = useState('');
  const [defaultFiles, setDefaultFiles] = useState(null);
  const [done,         setDone]         = useState(false);   // flashes to 100% before transition
  const intervalRef = useRef(null);

  const isLoading = status === 'loading';
  const elapsed   = useElapsed(isLoading);

  useEffect(() => {
    fetch(`${PAM_CONFIG.API_BASE}/default-files`)
      .then((r) => r.json())
      .then((d) => setDefaultFiles(d))
      .catch(() => setDefaultFiles(null));
  }, []);

  // ── Progress simulation ───────────────────────────────────────────────────
  // Nonlinear curve: fast early, decelerates toward 97% ceiling.
  // When real response arrives → immediately jumps to 100%.
  const startProgress = () => {
    const START = Date.now();
    // Adaptive ceiling: we never know exact duration, so use an asymptotic curve
    // progress = 97 * (1 - e^(-t / TAU))  →  approaches 97% but never reaches it
    const TAU = 90_000; // time constant in ms — ~90s to reach ~63%

    intervalRef.current = setInterval(() => {
      const t   = Date.now() - START;
      const pct = 97 * (1 - Math.exp(-t / TAU));
      setProgress(pct);
    }, 300);
  };

  const stopProgress = () => {
    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
  };

  const runAnalysis = async () => {
    setStatus('loading');
    setProgress(0);
    setDone(false);
    setError('');
    startProgress();

    try {
      const res = await fetch(`${PAM_CONFIG.API_BASE}/analyze-default`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server error ${res.status}`);
      }
      const data = await res.json();

      // Stop simulation, flash to 100%, then transition
      stopProgress();
      setProgress(100);
      setDone(true);

      setTimeout(() => {
        dispatch({ type: 'SET_APP_DATA', payload: data, sessionId: data.session_id || null });
        dispatch({ type: 'SHOW_TOAST', message: `${data.totalOrders || 0} orders analysed`, toastType: 'success' });
        runSummaryInBackground(data.session_id, dispatch);
        runClusterInsightsInBackground(data.session_id, dispatch);
      }, 700);

    } catch (err) {
      stopProgress();
      setStatus('error');
      setError(err.message || 'Could not connect to the backend. Make sure it is running on port 8001.');
    }
  };

  useEffect(() => () => stopProgress(), []);

  const hasFiles  = defaultFiles?.table_a?.exists;
  const fileLabel = hasFiles
    ? `${defaultFiles.table_a.name}${defaultFiles.table_b?.exists ? ` + ${defaultFiles.table_b.name}` : ''}`
    : null;

  const elapsedStr = elapsed < 60
    ? `${elapsed}s elapsed`
    : `${Math.floor(elapsed / 60)}m ${elapsed % 60}s elapsed`;

  return (
    <div className="splash-root">
      <ParticleCanvas analyzing={isLoading} />
      <Vignette />

      <div className="splash-content">

        {/* Logo */}
        <div className={`splash-logo-wrap ${isLoading ? 'logo-pulse' : ''}`}>
          <div className="splash-logo">OFI</div>
          <div className="splash-brand">Process Compliance Agent</div>
        </div>

        {/* Card */}
        <div className={`splash-card ${isLoading ? 'card-analyzing' : ''}`}>

          {/* IDLE */}
          {status === 'idle' && (
            <>
              <div>
                <div className="splash-title">Ready to Analyse</div>
                <div className="splash-sub" style={{ marginTop: 8 }}>
                  Run the compliance pipeline on your logistics data. The engine detects
                  deviations, scores every order, and generates AI-powered insights.
                </div>
              </div>

              {hasFiles && (
                <div className="splash-files-info">
                  <div className="splash-file-item">
                    <span className="splash-file-icon">◈</span>
                    {fileLabel}
                  </div>
                </div>
              )}

              {!hasFiles && defaultFiles !== null && (
                <div className="splash-error">
                  No data files found in <code>backend/data/</code>.<br />
                  Place your CSV/XLSX there and set <code>DEFAULT_TABLE_A</code> in <code>.env</code>.
                </div>
              )}

              <button className="splash-run-btn" onClick={runAnalysis} disabled={!hasFiles}>
                ▶ Run Analysis
              </button>
            </>
          )}

          {/* LOADING */}
          {isLoading && (
            <>
              <div>
                <div className="splash-title" style={{ fontSize: 15 }}>
                  {done ? 'Analysis Complete' : 'Pipeline Running'}
                </div>
                <div className="splash-sub" style={{ marginTop: 3, fontSize: 11 }}>
                  {done
                    ? 'Loading dashboard…'
                    : `${Math.round(progress)}% complete · ${elapsedStr}`}
                </div>
              </div>

              {/* Master bar */}
              <div className="splash-progress-master">
                <div className="splash-progress-master-fill" style={{ width: `${progress}%` }} />
                {!done && (
                  <div className="splash-progress-glow" style={{ left: `${Math.max(0, progress - 1)}%` }} />
                )}
              </div>

              {/* Step list */}
              {!done && <PipelineProgress progress={progress} />}

              {done && (
                <div style={{ fontSize: 13, color: 'rgba(204,162,62,.8)', letterSpacing: 1 }}>
                  ✓ All steps complete
                </div>
              )}
            </>
          )}

          {/* ERROR */}
          {status === 'error' && (
            <>
              <div className="splash-title">Analysis Failed</div>
              <div className="splash-error">{error}</div>
              <button className="splash-run-btn" onClick={() => setStatus('idle')}>← Try Again</button>
            </>
          )}
        </div>

        {status === 'idle' && (
          <div style={{ marginTop: 20, fontSize: 10, color: 'rgba(255,255,255,.15)', letterSpacing: 2, textTransform: 'uppercase' }}>
            Move cursor to interact
          </div>
        )}
      </div>
    </div>
  );
}
