// datasette-llm-sql-writer front-end
// Registers a panel above the table with a chat log and prompt input.

function getDbAndTableFromPath() {
  // Expect path like /{db}/{table} or with extra segments for filters
  const parts = window.location.pathname.split('/').filter(Boolean);
  if (parts.length >= 1) {
    const db = parts[0] || null;
    // Handle /{db}/-/query and similar: treat table as null when segment is '-'
    const second = parts.length >= 2 ? parts[1] : null;
    const table = (second && second !== '-') ? second : null;
    return { db, table };
  }
  return { db: null, table: null };
}

// --- State module (versioned, per-db) ---
const STATE_PREFIX = 'llm_sql_writer:state:v1';
const HISTORY_PREFIX = 'llm_sql_writer:history:v1';

function stateKey(db) {
  return `${STATE_PREFIX}:db:${db || 'global'}`;
}
function historyKey(db) {
  return `${HISTORY_PREFIX}:db:${db || 'global'}`;
}

function loadState(db) {
  try {
    const raw = localStorage.getItem(stateKey(db));
    if (!raw) return { panelCollapsed: false, modelId: null, lastSql: '', lastPrompt: '', lastRanSql: '' };
    const obj = JSON.parse(raw);
    return {
      panelCollapsed: !!obj.panelCollapsed,
      modelId: obj.modelId ?? null,
      lastSql: typeof obj.lastSql === 'string' ? obj.lastSql : '',
      lastPrompt: typeof obj.lastPrompt === 'string' ? obj.lastPrompt : '',
      lastRanSql: typeof obj.lastRanSql === 'string' ? obj.lastRanSql : ''
    };
  } catch (_) {
    return { panelCollapsed: false, modelId: null, lastSql: '', lastPrompt: '', lastRanSql: '' };
  }
}

function saveState(db, patch) {
  try {
    const prev = loadState(db);
    const next = { ...prev, ...patch };
    localStorage.setItem(stateKey(db), JSON.stringify(next));
    return next;
  } catch (_) { /* ignore */ }
}

function loadHistory(db) {
  try {
    const raw = localStorage.getItem(historyKey(db));
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr : [];
  } catch (_) {
    return [];
  }
}

function saveHistory(db, history) {
  try {
    const trimmed = Array.isArray(history) ? history.slice(-200) : [];
    localStorage.setItem(historyKey(db), JSON.stringify(trimmed));
  } catch (_) { /* ignore */ }
}

async function postJSON(url, data) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(data)
  });
  const text = await res.text();
  try {
    return { status: res.status, json: JSON.parse(text) };
  } catch (_) {
    return { status: res.status, json: { error: text } };
  }
}

function findSqlEditor() {
  // Try common selectors used by Datasette's SQL editor
  // 1) textarea[name="sql"]
  let textarea = document.querySelector('textarea[name="sql"]');
  if (textarea) return textarea;
  // 2) any element with data-sql-editor
  textarea = document.querySelector('textarea[data-sql-editor], [data-sql-editor] textarea');
  return textarea || null;
}

function findSqlFormContaining(textarea) {
  if (!textarea) return null;
  let el = textarea;
  while (el && el !== document.body) {
    if (el.tagName === 'FORM') return el;
    el = el.parentElement;
  }
  return null;
}

function renderPanel(node) {
  const { db, table } = getDbAndTableFromPath();
  let history = loadHistory(db);

  node.innerHTML = '';
  node.style.border = '1px solid #ddd';
  node.style.padding = '8px';
  node.style.marginBottom = '10px';

  const header = document.createElement('h3');
  header.textContent = '';
  header.style.margin = '0 0 6px 0';
  const toggle = document.createElement('a');
  toggle.href = '#';
  toggle.textContent = '(hide)';
  toggle.style.fontWeight = 'normal';
  toggle.style.fontSize = '0.9em';
  toggle.style.marginLeft = '6px';
  const headerLeft = document.createElement('span');
  headerLeft.textContent = 'LLM SQL Writer';
  header.innerHTML = '';
  header.appendChild(headerLeft);
  header.appendChild(document.createTextNode(' '));
  header.appendChild(toggle);

  const chatLog = document.createElement('div');
  chatLog.id = 'llm-sql-writer-chat';
  chatLog.style.maxHeight = '220px';
  chatLog.style.overflowY = 'auto';
  chatLog.style.marginBottom = '8px';

  const prompt = document.createElement('textarea');
  prompt.rows = 3;
  prompt.style.width = '100%';
  prompt.placeholder = 'Describe the query you want...';

  const btnRow = document.createElement('div');
  btnRow.style.marginTop = '6px';
  const genBtn = document.createElement('button');
  genBtn.textContent = 'Generate Only';
  const runBtn = document.createElement('button');
  runBtn.textContent = 'Generate & Run';
  runBtn.style.marginLeft = '6px';
  const spinner = document.createElement('span');
  spinner.textContent = 'Generating…';
  spinner.style.marginLeft = '8px';
  spinner.style.fontStyle = 'italic';
  spinner.style.opacity = '0.7';
  spinner.style.display = 'none';

  btnRow.appendChild(genBtn);
  btnRow.appendChild(runBtn);
  btnRow.appendChild(spinner);

  const contentBox = document.createElement('div');
  contentBox.appendChild(chatLog);
  contentBox.appendChild(prompt);
  contentBox.appendChild(btnRow);

  node.appendChild(header);
  node.appendChild(contentBox);

  let { lastSql } = loadState(db);

  // Persist panel collapsed/expanded state across navigations using state module
  function getPanelCollapsed() {
    return !!loadState(db).panelCollapsed;
  }
  function setPanelCollapsed(v) {
    saveState(db, { panelCollapsed: !!v });
  }

  function renderMessages(msgs) {
    chatLog.innerHTML = '';
    let currentUserCard = null;
    let currentResponses = null;
    msgs.forEach((m) => {
      if (m.role === 'user') {
        const userDiv = document.createElement('div');
        userDiv.style.background = '#d6ecff';
        userDiv.style.border = '1px solid #7db7ff';
        userDiv.style.borderRadius = '8px';
        userDiv.style.padding = '6px 8px';
        userDiv.style.margin = '6px 0';
        const content = document.createElement('div');
        content.style.color = '#084e8a';
        content.textContent = `• ${m.content}`;
        userDiv.appendChild(content);
        // Container for assistant responses to this prompt
        const responses = document.createElement('div');
        responses.style.marginLeft = '10px';
        responses.style.marginTop = '6px';
        userDiv.appendChild(responses);
        chatLog.appendChild(userDiv);
        currentUserCard = userDiv;
        currentResponses = responses;
      } else {
        // Assistant message: treat SQL specially unless it's an error
        const target = currentResponses || chatLog;
        const isError = typeof m.content === 'string' && m.content.startsWith('ERROR:');
        if (isError) {
          const div = document.createElement('div');
          div.style.background = '#ffd6d6';
          div.style.border = '1px solid #ff9c9c';
          div.style.borderRadius = '8px';
          div.style.padding = '6px 8px';
          div.style.margin = '6px 0';
          const content = document.createElement('div');
          content.textContent = m.content;
          div.appendChild(content);
          target.appendChild(div);
        } else {
          const div = document.createElement('div');
          div.style.background = '#ece6ff';
          div.style.border = '1px solid #b5a8ff';
          div.style.borderRadius = '8px';
          div.style.padding = '6px 8px';
          div.style.margin = '6px 0';
          const details = document.createElement('details');
          details.open = false;
          const summary = document.createElement('summary');
          // Make summary a flex row so actions can sit on the same line
          summary.style.display = 'flex';
          summary.style.alignItems = 'center';
          const summaryText = document.createElement('span');
          const lines = (m.content || '').split('\n').length;
          function setSummaryText() {
            if (details.open) {
              summaryText.innerHTML = '<em>Hide SQL</em>';
            } else {
              summaryText.innerHTML = `<em>Show SQL (${lines} lines)</em>`;
            }
          }
          setSummaryText();
          details.addEventListener('toggle', setSummaryText);
          const pre = document.createElement('pre');
          pre.style.whiteSpace = 'pre-wrap';
          pre.style.marginTop = '6px';
          pre.textContent = m.content || '';
          details.appendChild(summary);
          details.appendChild(pre);

          // Action buttons inline with summary
          const actions = document.createElement('div');
          actions.style.marginLeft = 'auto';
          actions.style.display = 'flex';
          actions.style.alignItems = 'center';
          actions.style.gap = '6px';
          const copyBtn = document.createElement('button');
          copyBtn.type = 'button';
          copyBtn.title = 'Copy SQL to clipboard';
          copyBtn.setAttribute('aria-label', 'Copy SQL to clipboard');
          // Inline SVG icon for Copy (from static/copy_icon.svg)
          copyBtn.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
              <path d="
                    M 6 6
                    L 6 4
                    A 1 1 0 0 1 7 3
                    L 14 3
                    A 1 1 0 0 1 15 4
                    L 15 14
                    A 1 1 0 0 1 14 15
                    L 12 15
                  "
                    fill="none" 
                    stroke="#4b5563" 
                    stroke-width="1.5" 
                    stroke-linecap="round" 
                    stroke-linejoin="round"/>
              <rect x="3" y="6" width="9" height="12" rx="1" ry="1" 
                    fill="none" 
                    stroke="#4b5563" 
                    stroke-width="1.5"/>
            </svg>
          `;
          const runBtn2 = document.createElement('button');
          runBtn2.type = 'button';
          runBtn2.title = 'Run SQL';
          runBtn2.setAttribute('aria-label', 'Run SQL');
          // Inline SVG icon for Run (from static/play_icon.svg)
          runBtn2.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
              <polygon points="6,4 6,16 15,10" fill="#4b5563"/>
            </svg>
          `;

          // (Copy icon is inlined above)
          actions.appendChild(copyBtn);
          actions.appendChild(runBtn2);

          copyBtn.addEventListener('click', async (ev) => {
            ev.preventDefault(); ev.stopPropagation();
            const sql = m.content || '';
            try {
              if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(sql);
              } else {
                // Fallback
                const ta = document.createElement('textarea');
                ta.value = sql;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
              }
            } catch (_) { /* ignore copy errors */ }
          });

          runBtn2.addEventListener('click', (ev) => {
            ev.preventDefault(); ev.stopPropagation();
            const sql = m.content || '';
            runArbitrarySql(sql);
          });

          summary.appendChild(summaryText);
          summary.appendChild(actions);
          details.appendChild(summary);
          details.appendChild(pre);
          div.appendChild(details);
          target.appendChild(div);
        }
      }
    });
  }

  renderMessages(history);

  toggle.addEventListener('click', (ev) => {
    ev.preventDefault();
    const isHidden = contentBox.style.display === 'none';
    contentBox.style.display = isHidden ? '' : 'none';
    toggle.textContent = isHidden ? '(hide)' : '(show)';
    setPanelCollapsed(!isHidden);
  });

  // Initialize panel visibility from saved state
  (function initPanelVisibility() {
    const collapsed = getPanelCollapsed();
    contentBox.style.display = collapsed ? 'none' : '';
    toggle.textContent = collapsed ? '(show)' : '(hide)';
  })();

  // Keep UI in sync across tabs/windows
  window.addEventListener('storage', (e) => {
    const hKey = historyKey(db);
    const sKey = stateKey(db);
    if (e.key === hKey) {
      history = loadHistory(db);
      renderMessages(history);
    } else if (e.key === sKey) {
      const collapsed = getPanelCollapsed();
      contentBox.style.display = collapsed ? 'none' : '';
      toggle.textContent = collapsed ? '(show)' : '(hide)';
      // Also update lastSql
      lastSql = loadState(db).lastSql || '';
    }
  });

  async function generate() {
    const p = prompt.value.trim();
    if (!db || !p) return;
    const newHistory = history.concat([{ role: 'user', content: p }]);
    renderMessages(newHistory);
    genBtn.disabled = true; runBtn.disabled = true; spinner.style.display = '';
    const { status, json } = await postJSON('/-/llm-sql-writer/generate', {
      db, table, prompt: p, history: newHistory
    });
    try {
      if (status === 200 && json.sql) {
        lastSql = json.sql;
        newHistory.push({ role: 'assistant', content: json.sql });
        saveHistory(db, newHistory);
        saveState(db, { lastSql, lastPrompt: p });
        history = newHistory;
        renderMessages(newHistory);
        const editor = findSqlEditor();
        if (editor) editor.value = lastSql;
      } else {
        const msg = json && json.error ? json.error : `Error ${status}`;
        newHistory.push({ role: 'assistant', content: `ERROR: ${msg}` });
        renderMessages(newHistory);
      }
    } finally {
      spinner.style.display = 'none';
      genBtn.disabled = false; runBtn.disabled = false;
    }
  }

  async function generateAndRun() {
    const p = prompt.value.trim();
    const st = loadState(db);
    const editor = findSqlEditor();
    const editorSql = editor ? (editor.value || '').trim() : '';
    const lastRan = (st.lastRanSql || st.lastSql || '').trim();
    let needRegenerate = false;
    // Regenerate if prompt changed or editor contents differ from last run/generated SQL
    if (p !== (st.lastPrompt || '')) {
      needRegenerate = true;
    } else if (editor && editorSql && editorSql !== lastRan) {
      needRegenerate = true;
    } else if (!lastSql) {
      needRegenerate = true;
    }

    if (needRegenerate) {
      await generate();
      // Refresh lastSql after generate (generate saves to state too)
      lastSql = (loadState(db).lastSql || '').trim();
      if (!lastSql) return;
    }

    if (editor) editor.value = lastSql;
    const form = findSqlFormContaining(editor);
    if (form) {
      // Save lastRanSql and lastPrompt before submitting
      saveState(db, { lastRanSql: lastSql, lastPrompt: p });
      form.submit();
    } else {
      // No visible editor/form (likely due to _hide_sql=1). Redirect to run.
      const { db: dbName } = getDbAndTableFromPath();
      if (!dbName) return;
      // Save lastRanSql and lastPrompt before redirecting
      saveState(dbName, { lastRanSql: lastSql, lastPrompt: p });
      const url = `/${encodeURIComponent(dbName)}/-/query?sql=${encodeURIComponent(lastSql)}&_hide_sql=1`;
      window.location.href = url;
    }
  }

  // Run arbitrary SQL either by inserting into the visible editor and submitting
  // the form, or by redirecting to the query page when the editor is hidden.
  function runArbitrarySql(sql) {
    if (!sql) return;
    const editor = findSqlEditor();
    if (editor) editor.value = sql;
    const form = findSqlFormContaining(editor);
    if (form) {
      saveState(db, { lastRanSql: sql });
      form.submit();
    } else {
      const url = `/${encodeURIComponent(db)}/-/query?sql=${encodeURIComponent(sql)}&_hide_sql=1`;
      saveState(db, { lastRanSql: sql });
      window.location.href = url;
    }
  }

  genBtn.addEventListener('click', generate);
  runBtn.addEventListener('click', (ev) => { ev.preventDefault(); generateAndRun(); });
}

// Register as a JavaScript plugin so the panel appears on table pages
// Requires Datasette 1.x JavaScript plugin API

document.addEventListener('datasette_init', function (ev) {
  const manager = ev.detail;
  const { db, table } = getDbAndTableFromPath();
  if (db && table) {
    // Table page: use Datasette's panel API
    manager.registerPlugin('datasette-llm-sql-writer', {
      version: 0.1,
      makeAboveTablePanelConfigs: () => {
        return [
          {
            id: 'llm-sql-writer-panel',
            label: 'LLM SQL Writer',
            render: renderPanel
          }
        ];
      }
    });
  } else {
    // Non-table pages: always insert the panel under the first <h1> in the content section
    if (!document.getElementById('llm-sql-writer-panel')) {
      const container = document.createElement('div');
      container.id = 'llm-sql-writer-panel';
      renderPanel(container);
      const section = document.querySelector('section.content') || document.querySelector('.content');
      if (section) {
        const headerH1 = section.querySelector('h1');
        if (headerH1 && headerH1.parentNode) {
          if (headerH1.nextSibling) {
            headerH1.parentNode.insertBefore(container, headerH1.nextSibling);
          } else {
            headerH1.parentNode.appendChild(container);
          }
        } else {
          section.appendChild(container);
        }
      } else {
        // As a last resort, add to body top
        document.body.insertBefore(container, document.body.firstChild);
      }
    }
  }
});
