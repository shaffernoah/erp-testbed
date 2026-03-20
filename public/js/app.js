/* ============================================================
   LaFrieda ERP Agent - Chat & SSE (Vercel Edition)
   API key stored in sessionStorage, sent via X-API-Key header
   ============================================================ */

var currentPersona = 'vendor_ops';
var conversationHistory = [];
var isStreaming = false;
var currentIteration = null;

// ---- API Key Management ----
function getApiKey() {
  return sessionStorage.getItem('anthropic_api_key') || '';
}

function saveApiKey() {
  var key = document.getElementById('api-key-input').value.trim();
  if (!key) return;
  if (!key.startsWith('sk-ant-')) {
    alert('Please enter a valid Anthropic API key (starts with sk-ant-)');
    return;
  }
  sessionStorage.setItem('anthropic_api_key', key);
  document.getElementById('api-key-banner').style.display = 'none';
  document.getElementById('api-key-connected').style.display = 'flex';
  document.getElementById('msg-input').focus();
}

function changeApiKey() {
  sessionStorage.removeItem('anthropic_api_key');
  document.getElementById('api-key-banner').style.display = 'flex';
  document.getElementById('api-key-connected').style.display = 'none';
  document.getElementById('api-key-input').value = '';
  document.getElementById('api-key-input').focus();
}

function checkApiKey() {
  var key = getApiKey();
  if (key) {
    document.getElementById('api-key-banner').style.display = 'none';
    document.getElementById('api-key-connected').style.display = 'flex';
  } else {
    document.getElementById('api-key-banner').style.display = 'flex';
    document.getElementById('api-key-connected').style.display = 'none';
  }
}

// Allow Enter key in API key input
document.getElementById('api-key-input').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    saveApiKey();
  }
});

// ---- Persona config ----
var personaInfo = {
  vendor_ops: {
    title: 'Operations Manager',
    desc: 'Identify value at risk, optimize inventory, routes, and margins through proactive micro-actions.',
    tools: ['query_database', 'check_alerts', 'slow_mover_scanner', 'route_optimizer', 'profit_opportunity_scanner', 'optimize_inventory', 'get_reorder_suggestions', 'generate_campaign', 'optimize_payments', 'handle_dispute'],
    quickActions: [
      { icon: '\u2600', label: 'Daily Briefing', query: 'Give me a full operational briefing. Scan alerts, slow movers, route efficiency, and reorder needs.' },
      { icon: '\u23F2', label: 'Scan Slow Movers', query: 'Scan for inventory sitting 3+ weeks without movement. Show me value at risk and recovery campaigns.' },
      { icon: '\u25B6', label: 'Route Report', query: 'Analyze route efficiency across all active routes. Find underutilized routes and merge candidates.' },
      { icon: '\u26A0', label: 'Reorder Check', query: 'Check for SKUs approaching stockout. What needs to be reordered and from which suppliers?' },
    ],
    examples: [
      'Give me a full daily operational briefing with alerts, slow movers, and route efficiency.',
      'What inventory is sitting idle and losing value? Build campaigns to move it.',
      'Which routes are underperforming and what can we do about it?',
      'What are our highest-margin undersold products? Who should we push them to?',
    ]
  },
  vendor_sales: {
    title: 'Sales Intelligence',
    desc: 'Drive incremental revenue through targeted campaigns, wallet share growth, and proactive customer outreach.',
    tools: ['query_database', 'profit_opportunity_scanner', 'slow_mover_scanner', 'generate_campaign', 'check_alerts', 'optimize_payments'],
    quickActions: [
      { icon: '\u2197', label: 'Revenue Opportunities', query: 'Scan for high-margin undersold products. Who should we target and what campaigns should we run?' },
      { icon: '\u26A0', label: 'At-Risk Accounts', query: 'Which accounts show signs of churn? Build win-back campaigns with dollar impact.' },
      { icon: '\u2728', label: 'Campaign Ideas', query: 'What campaigns should we launch this week based on inventory, margin, and customer data?' },
      { icon: '\u23F2', label: 'Slow Mover Push', query: 'Find slow-moving inventory and build targeted campaigns to move it through past buyers.' },
    ],
    examples: [
      'Where can we drive the most incremental margin? Show me specific accounts and campaigns.',
      'Which Cari-enrolled accounts show signs of churn? Build a win-back campaign.',
      'What slow-moving inventory can we convert into customer loyalty touchpoints?',
      'Give me the top 10 accounts by revenue. How is their wallet share and what can we grow?',
    ]
  },
  restaurant: {
    title: 'Restaurant Buyer',
    desc: 'Maximize Cari cashback, catch invoice errors, resolve disputes, and optimize every payment dollar.',
    tools: ['query_database', 'optimize_payments', 'handle_dispute'],
    quickActions: [
      { icon: '\uD83D\uDCB0', label: 'Optimize Payments', query: 'Analyze all open invoices and give me the optimal payment schedule to maximize Cari cashback.' },
      { icon: '\uD83D\uDCCB', label: 'Review Invoices', query: 'Pull my recent invoices and check for catch weight variances, pricing discrepancies, and anything unusual.' },
      { icon: '\u2B50', label: 'Cari Rewards Status', query: 'What is my current Cari tier, points balance, and how close am I to the next tier? How much more do I need to spend?' },
      { icon: '\u26A0', label: 'File a Dispute', query: 'Help me review my most recent invoice for any issues and file a dispute if needed.' },
    ],
    examples: [
      'Optimize my payment schedule to maximize Cari cashback rewards.',
      'Review my recent invoices for catch weight variances or pricing errors.',
      'What is my Cari reward tier and how do I maximize my cashback this month?',
      'I received short-weight on my last delivery. Help me file a dispute.',
    ]
  }
};

// ---- Tool color categories ----
var toolCategories = {
  query_database: 'query',
  check_alerts: 'alert',
  slow_mover_scanner: 'analysis',
  route_optimizer: 'analysis',
  profit_opportunity_scanner: 'analysis',
  optimize_inventory: 'action',
  generate_campaign: 'action',
  optimize_payments: 'action',
  get_reorder_suggestions: 'resolve',
  handle_dispute: 'resolve',
};

// ---- Init ----
document.addEventListener('DOMContentLoaded', function() {
  checkApiKey();
  updatePersona(currentPersona);
  setupEventListeners();
});

function setupEventListeners() {
  // Persona tabs
  document.querySelectorAll('.persona-tab').forEach(function(btn) {
    btn.addEventListener('click', function() {
      if (isStreaming) return;
      document.querySelectorAll('.persona-tab').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      currentPersona = btn.dataset.persona;
      conversationHistory = [];
      resetChat();
      updatePersona(currentPersona);
    });
  });

  // Trace toggle
  document.getElementById('trace-toggle').addEventListener('change', function() {
    document.body.classList.toggle('hide-trace', !this.checked);
  });

  // New chat
  document.getElementById('new-chat-btn').addEventListener('click', function() {
    if (isStreaming) return;
    conversationHistory = [];
    resetChat();
  });

  // Input
  var input = document.getElementById('msg-input');
  input.addEventListener('input', function() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  });
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
}

function updatePersona(persona) {
  var info = personaInfo[persona];
  if (!info) return;

  document.getElementById('persona-title').textContent = info.title;
  document.getElementById('persona-desc').textContent = info.desc;

  var toolsDiv = document.getElementById('persona-tools');
  toolsDiv.innerHTML = '';
  info.tools.forEach(function(t) {
    var chip = document.createElement('span');
    chip.className = 'tool-chip';
    chip.textContent = t;
    toolsDiv.appendChild(chip);
  });

  var qaDiv = document.getElementById('quick-actions');
  qaDiv.innerHTML = '';
  info.quickActions.forEach(function(qa) {
    var btn = document.createElement('button');
    btn.className = 'quick-action-btn';
    btn.innerHTML = '<span class="quick-action-icon">' + qa.icon + '</span>' + qa.label;
    btn.addEventListener('click', function() {
      document.getElementById('msg-input').value = qa.query;
      sendMessage();
    });
    qaDiv.appendChild(btn);
  });

  var exDiv = document.getElementById('welcome-examples');
  if (exDiv) {
    exDiv.innerHTML = '';
    info.examples.forEach(function(ex) {
      var btn = document.createElement('button');
      btn.className = 'example-btn';
      btn.textContent = ex;
      btn.addEventListener('click', function() {
        document.getElementById('msg-input').value = ex;
        sendMessage();
      });
      exDiv.appendChild(btn);
    });
  }
}

function resetChat() {
  var container = document.getElementById('chat-container');
  container.innerHTML = '';
  var welcome = document.createElement('div');
  welcome.className = 'welcome';
  welcome.id = 'welcome';
  welcome.innerHTML = '<div class="welcome-icon">LF</div>' +
    '<h2>LaFrieda ERP Agent</h2>' +
    '<p>AI-powered operations intelligence. Ask questions, get proactive recommendations with dollar-quantified impact.</p>' +
    '<div class="welcome-examples" id="welcome-examples"></div>';
  container.appendChild(welcome);
  updatePersona(currentPersona);
}

// ---- Markdown rendering ----
function renderMarkdown(text) {
  if (typeof marked !== 'undefined') {
    marked.setOptions({
      breaks: true,
      gfm: true,
      highlight: function(code, lang) {
        if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang)) {
          return hljs.highlight(code, { language: lang }).value;
        }
        return code;
      }
    });
    return marked.parse(text);
  }
  var html = escapeHtml(text);
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\n/g, '<br>');
  return html;
}

function escapeHtml(text) {
  var div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

// ---- Chat UI ----
function scrollToBottom() {
  var container = document.getElementById('chat-container');
  container.scrollTop = container.scrollHeight;
}

function addMessage(role, content) {
  var container = document.getElementById('chat-container');
  var welcome = document.getElementById('welcome');
  if (welcome) welcome.remove();

  var div = document.createElement('div');
  div.className = 'message ' + role;
  if (role === 'assistant') {
    div.innerHTML = '<div class="md-content">' + renderMarkdown(content) + '</div>';
  } else {
    div.textContent = content;
  }
  container.appendChild(div);
  scrollToBottom();
  return div;
}

function addTrace(type, content) {
  var container = document.getElementById('chat-container');

  if (type === 'thinking') {
    var iterDiv = document.createElement('div');
    iterDiv.className = 'trace-iteration';

    var header = document.createElement('div');
    header.className = 'trace-iter-header';
    header.innerHTML = '<span class="iter-arrow">\u25B6</span> ' + escapeHtml(String(content));
    header.addEventListener('click', function() {
      header.classList.toggle('open');
      var body = header.nextElementSibling;
      if (body) body.classList.toggle('open');
    });

    var body = document.createElement('div');
    body.className = 'trace-iter-body';

    iterDiv.appendChild(header);
    iterDiv.appendChild(body);
    container.appendChild(iterDiv);
    currentIteration = body;
    scrollToBottom();
    return;
  }

  if (!currentIteration) {
    var iterDiv = document.createElement('div');
    iterDiv.className = 'trace-iteration';
    var body = document.createElement('div');
    body.className = 'trace-iter-body open';
    iterDiv.appendChild(body);
    container.appendChild(iterDiv);
    currentIteration = body;
  }

  var toolDiv = document.createElement('div');
  var toolName = content.name || '';
  var category = toolCategories[toolName] || 'query';
  toolDiv.className = 'trace-tool ' + category;

  if (type === 'tool_call') {
    toolDiv.innerHTML = '<span class="trace-tool-name">' + escapeHtml(toolName) + '</span>' +
      '<span class="trace-tool-status">called</span>';
    currentIteration.classList.add('open');
    var header = currentIteration.previousElementSibling;
    if (header) header.classList.add('open');
  } else if (type === 'tool_result') {
    toolDiv.innerHTML = '<span class="trace-tool-name">' + escapeHtml(toolName) + '</span>' +
      '<span class="trace-tool-status">\u2713 returned</span>';
  }

  currentIteration.appendChild(toolDiv);
  scrollToBottom();
}

function addTypingIndicator() {
  removeTypingIndicator();
  var container = document.getElementById('chat-container');
  var div = document.createElement('div');
  div.className = 'typing-indicator';
  div.id = 'typing';
  div.innerHTML = '<span></span><span></span><span></span>';
  container.appendChild(div);
  scrollToBottom();
}

function removeTypingIndicator() {
  var el = document.getElementById('typing');
  if (el) el.remove();
}

// ---- SSE handling ----
function handleSSELine(line, msg) {
  if (!line.startsWith('data: ')) return;
  var jsonStr = line.substring(6);
  if (!jsonStr || jsonStr.trim() === '') return;

  try {
    var event = JSON.parse(jsonStr);
  } catch(e) {
    return;
  }

  if (event.type === 'thinking') {
    removeTypingIndicator();
    addTrace('thinking', event.content);
    addTypingIndicator();
  } else if (event.type === 'tool_call') {
    removeTypingIndicator();
    addTrace('tool_call', event);
    addTypingIndicator();
  } else if (event.type === 'tool_result') {
    removeTypingIndicator();
    addTrace('tool_result', event);
    addTypingIndicator();
  } else if (event.type === 'answer') {
    removeTypingIndicator();
    currentIteration = null;
    addMessage('assistant', event.content);

    var container = document.getElementById('chat-container');
    var stats = document.createElement('div');
    stats.className = 'stats-bar';
    stats.innerHTML = '<span>' + event.tool_calls + ' tool calls</span>' +
      '<span>' + event.elapsed + 's</span>' +
      '<span>' + event.iterations + ' iterations</span>';
    container.appendChild(stats);
    scrollToBottom();

    conversationHistory.push({role: 'user', content: msg});
    conversationHistory.push({role: 'assistant', content: event.content});
  }
}

// ---- Send message ----
function sendMessage() {
  var input = document.getElementById('msg-input');
  var msg = input.value.trim();
  if (!msg || isStreaming) return;

  var apiKey = getApiKey();
  if (!apiKey) {
    document.getElementById('api-key-banner').style.display = 'flex';
    document.getElementById('api-key-input').focus();
    return;
  }

  isStreaming = true;
  document.getElementById('send-btn').disabled = true;
  input.value = '';
  input.style.height = 'auto';
  currentIteration = null;

  addMessage('user', msg);
  addTypingIndicator();

  var xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/chat', true);
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.setRequestHeader('X-API-Key', apiKey);

  var seenLength = 0;

  xhr.onprogress = function() {
    var newText = xhr.responseText.substring(seenLength);
    seenLength = xhr.responseText.length;
    var lines = newText.split('\n');
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      if (line) handleSSELine(line, msg);
    }
  };

  xhr.onload = function() {
    // Check for auth error
    if (xhr.status === 401) {
      removeTypingIndicator();
      addMessage('assistant', 'Missing or invalid API key. Please enter your Anthropic API key above.');
      changeApiKey();
      isStreaming = false;
      document.getElementById('send-btn').disabled = false;
      return;
    }

    var remaining = xhr.responseText.substring(seenLength);
    if (remaining) {
      var lines = remaining.split('\n');
      for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (line) handleSSELine(line, msg);
      }
    }
    removeTypingIndicator();
    isStreaming = false;
    document.getElementById('send-btn').disabled = false;
    input.focus();
  };

  xhr.onerror = function() {
    removeTypingIndicator();
    addMessage('assistant', 'Connection error. Please try again.');
    isStreaming = false;
    document.getElementById('send-btn').disabled = false;
  };

  xhr.timeout = 300000;
  xhr.ontimeout = function() {
    removeTypingIndicator();
    addMessage('assistant', 'Request timed out.');
    isStreaming = false;
    document.getElementById('send-btn').disabled = false;
  };

  xhr.send(JSON.stringify({
    message: msg,
    persona: currentPersona,
    history: conversationHistory
  }));
}

// Global for KPI click
function kpiClick(type) {
  var queries = {
    expiry: 'What inventory is at risk of expiring in the next 7 days? Show me lots, values, and recommended actions.',
    slow_movers: 'Scan for slow-moving inventory sitting 3+ weeks. Show me value at risk and recovery campaigns.',
    routes: 'Analyze all delivery routes for efficiency. Find underutilized routes and merge candidates.',
    margin: 'Scan for high-margin undersold products. Who should we target to drive incremental profit?'
  };
  if (queries[type]) {
    document.getElementById('msg-input').value = queries[type];
    sendMessage();
  }
}
