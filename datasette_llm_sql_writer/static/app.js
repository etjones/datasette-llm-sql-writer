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

function getStorageKey(db, table) {
  // Single global history for all pages
  return 'llm_sql_writer:global';
}

function loadHistory() {
  try {
    const raw = localStorage.getItem(getStorageKey());
    if (!raw) return [];
    const arr = JSON.parse(raw);
    if (Array.isArray(arr)) return arr;
  } catch (_) { }
  return [];
}

function saveHistory(history) {
  try {
    localStorage.setItem(getStorageKey(), JSON.stringify(history || []));
  } catch (_) { }
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
  const history = loadHistory();

  node.innerHTML = '';
  node.style.border = '1px solid #ddd';
  node.style.padding = '8px';
  node.style.marginBottom = '10px';

  const chatLog = document.createElement('textarea');
  chatLog.rows = 6;
  chatLog.style.width = '100%';
  chatLog.placeholder = 'LLM chat log...';
  chatLog.readOnly = true;
  chatLog.value = history.map(m => `${m.role.toUpperCase()}: ${m.content}`).join('\n');

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

  btnRow.appendChild(genBtn);
  btnRow.appendChild(runBtn);

  node.appendChild(chatLog);
  node.appendChild(prompt);
  node.appendChild(btnRow);

  let lastSql = '';

  async function generate() {
    const p = prompt.value.trim();
    if (!db || !p) return;
    const newHistory = history.concat([{ role: 'user', content: p }]);
    chatLog.value = newHistory.map(m => `${m.role.toUpperCase()}: ${m.content}`).join('\n');
    const { status, json } = await postJSON('/-/llm-sql-writer/generate', {
      db, table, prompt: p, history: newHistory
    });
    if (status === 200 && json.sql) {
      lastSql = json.sql;
      newHistory.push({ role: 'assistant', content: json.sql });
      saveHistory(newHistory);
      chatLog.value = newHistory.map(m => `${m.role.toUpperCase()}: ${m.content}`).join('\n');
      const editor = findSqlEditor();
      if (editor) editor.value = lastSql;
    } else {
      const msg = json && json.error ? json.error : `Error ${status}`;
      newHistory.push({ role: 'assistant', content: `ERROR: ${msg}` });
      chatLog.value = newHistory.map(m => `${m.role.toUpperCase()}: ${m.content}`).join('\n');
    }
  }

  async function generateAndRun() {
    if (!lastSql) {
      await generate();
    }
    if (!lastSql) return;
    const editor = findSqlEditor();
    if (editor) editor.value = lastSql;
    const form = findSqlFormContaining(editor);
    if (form) form.submit();
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
    // Non-table pages: if a SQL editor exists (e.g. /{db}/-/query), inject our panel before it
    const editor = findSqlEditor();
    if (editor && !document.getElementById('llm-sql-writer-panel')) {
      const form = findSqlFormContaining(editor);
      const container = document.createElement('div');
      container.id = 'llm-sql-writer-panel';
      // Render our UI into the container and insert above the form/editor
      renderPanel(container);
      if (form && form.parentNode) {
        form.parentNode.insertBefore(container, form);
      } else if (editor.parentNode) {
        editor.parentNode.insertBefore(container, editor);
      }
    }
  }
});
