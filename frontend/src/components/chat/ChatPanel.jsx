import { useEffect, useRef, useState } from 'react';
import { useApp } from '../../context/AppContext.jsx';
import PAM_CONFIG from '../../config.js';
import ChatMessage from './ChatMessage.jsx';

const SUGGESTIONS = [
  { icon: '⚠', text: 'What are the top risk orders?' },
  { icon: '📍', text: 'Which locations had the most delays?' },
  { icon: '📊', text: 'Give me a compliance summary' },
  { icon: '🔎', text: 'Show deviation breakdown' },
  { icon: '📦', text: 'Which orders used wrong source locations?' },
  { icon: '📅', text: 'How many orders are delayed?' },
];

export default function ChatPanel() {
  const { state, dispatch } = useApp();
  const { chatOpen, chatHistory, sessionId } = state;
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef   = useRef(null);
  const inputRef    = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory]);

  // Focus input when panel opens
  useEffect(() => {
    if (chatOpen) setTimeout(() => inputRef.current?.focus(), 80);
  }, [chatOpen]);

  if (!chatOpen) return null;

  const sendMessage = async (question) => {
    const q = (question || input).trim();
    if (!q || loading) return;
    setInput('');

    dispatch({ type: 'ADD_CHAT_MESSAGE', payload: { role: 'user', content: q } });
    // Add empty AI message — loading=true shows typing indicator until first chunk
    dispatch({ type: 'ADD_CHAT_MESSAGE', payload: { role: 'ai', content: '', loading: true } });
    setLoading(true);

    try {
      const res = await fetch(`${PAM_CONFIG.API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, session_id: sessionId }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Error ${res.status}`);
      }

      // Read SSE stream — each line is "data: {...}\n\n"
      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let   buffer  = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE events are separated by double newline
        const parts = buffer.split('\n\n');
        buffer = parts.pop();          // keep incomplete event in buffer

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith('data: ')) continue;
          try {
            const event = JSON.parse(line.slice(6));

            if (event.type === 'chunk') {
              dispatch({ type: 'APPEND_CHAT_CHUNK', payload: event.text });
            } else if (event.type === 'data') {
              dispatch({ type: 'SET_CHAT_TABLE', payload: event.payload });
            } else if (event.type === 'done') {
              dispatch({
                type: 'UPDATE_LAST_CHAT_MESSAGE',
                payload: { source: event.source || 'ai', loading: false },
              });
            }
          } catch (_) { /* malformed SSE line — skip */ }
        }
      }
    } catch (err) {
      dispatch({
        type: 'UPDATE_LAST_CHAT_MESSAGE',
        payload: { content: `Sorry, something went wrong: ${err.message}`, loading: false, source: 'error' },
      });
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="chat-panel">
      {/* Header */}
      <div className="chat-header">
        <div className="chat-header-left">
          <div className="chat-header-dot" />
          <div>
            <div className="chat-header-title">Compliance Co-pilot</div>
            <div className="chat-header-sub">Powered by local AI · your data stays private</div>
          </div>
        </div>
        <button className="chat-close-btn" onClick={() => dispatch({ type: 'CLOSE_CHAT' })}>✕</button>
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {chatHistory.length === 0 && (
          <div className="chat-empty">
            <div className="chat-empty-icon">⬡</div>
            <div className="chat-empty-title">Your compliance co-pilot</div>
            <div className="chat-empty-sub">
              Ask about specific orders, deviation patterns, delays, or anything in the data.
            </div>
            <div className="chat-suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s.text} className="chat-suggestion" onClick={() => sendMessage(s.text)}>
                  <span className="chat-suggestion-icon">{s.icon}</span>
                  {s.text}
                </button>
              ))}
            </div>
          </div>
        )}

        {chatHistory.map((msg, i) => (
          <ChatMessage key={i} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="chat-input-row">
        <input
          ref={inputRef}
          className="chat-input"
          placeholder={sessionId ? 'Ask anything about your data…' : 'Upload data first…'}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={loading || !sessionId}
        />
        <button
          className="chat-send-btn"
          onClick={() => sendMessage()}
          disabled={loading || !input.trim() || !sessionId}
        >
          {loading ? <span className="chat-send-spinner" /> : '↑'}
        </button>
      </div>
    </div>
  );
}
