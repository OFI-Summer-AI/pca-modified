// Render simple markdown: **bold**, - bullet lines, \n line breaks
function renderText(text) {
  if (!text) return null;
  const lines = text.split('\n');
  const elements = [];
  let key = 0;

  const renderInline = (str) => {
    // Split on **bold** markers
    const parts = str.split(/\*\*(.+?)\*\*/g);
    return parts.map((part, i) =>
      i % 2 === 1 ? <strong key={i}>{part}</strong> : part
    );
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() === '') {
      // Empty line → small gap (skip consecutive empties)
      if (i > 0 && lines[i - 1].trim() !== '') {
        elements.push(<div key={key++} style={{ height: 6 }} />);
      }
    } else if (line.trim().startsWith('- ') || line.trim().startsWith('• ')) {
      elements.push(
        <div key={key++} className="chat-bullet">
          <span className="chat-bullet-dot">·</span>
          <span>{renderInline(line.trim().replace(/^[-•]\s*/, ''))}</span>
        </div>
      );
    } else {
      elements.push(
        <div key={key++} className="chat-line">{renderInline(line)}</div>
      );
    }
  }
  return elements;
}

const SOURCE_LABEL = {
  structured: 'structured query',
  local:      'instant',
  ai:         'AI',
  gemini:     'AI',
  pandas:     'structured query',
  error:      'error',
};

export default function ChatMessage({ message }) {
  const isUser = message.role === 'user';

  return (
    <div className={`chat-message ${isUser ? 'chat-message-user' : 'chat-message-ai'}`}>
      <div className="chat-bubble">
        {message.loading ? (
          <div className="chat-typing">
            <span /><span /><span />
          </div>
        ) : (
          <>
            <div className="chat-text">
              {isUser ? message.content : renderText(message.content)}
            </div>

            {message.data?.table && message.data.table.length > 0 && (
              <div className="chat-table-wrap">
                <table className="chat-table">
                  <thead>
                    <tr>
                      {Object.keys(message.data.table[0]).map((col) => (
                        <th key={col}>{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {message.data.table.slice(0, 12).map((row, i) => (
                      <tr key={i}>
                        {Object.values(row).map((val, j) => (
                          <td key={j}>{val ?? '—'}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {!isUser && message.source && message.source !== 'error' && (
              <div className="chat-source-badge">
                {SOURCE_LABEL[message.source] || message.source}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
