var currentPersona = 'vendor_ops';
var conversationHistory = [];
var isStreaming = false;

// Persona descriptions
var personaInfo = {
  vendor_ops: {
    title: 'Vendor Operations Agent',
    desc: 'Food safety, spoilage prevention, inventory optimization, replenishment planning, and operational alerting. Monitors lot expirations, temperature compliance, FIFO discipline, and warehouse zone transfers.',
    tools: ['query_database', 'check_alerts', 'optimize_inventory', 'get_reorder_suggestions', 'generate_campaign', 'handle_dispute', 'optimize_payments']
  },
  vendor_sales: {
    title: 'Vendor Sales Agent',
    desc: 'Customer intelligence, revenue growth, Cari Rewards campaign execution, and competitive pricing analysis. Identifies upsell opportunities, churn risk, and designs targeted promotions to drive volume and loyalty.',
    tools: ['query_database', 'generate_campaign', 'check_alerts', 'optimize_payments']
  },
  restaurant: {
    title: 'Restaurant Buyer Agent',
    desc: 'Payment optimization, invoice verification, dispute resolution, and spend analytics. Helps restaurant accounts maximize Cari cashback, verify catch weights, and manage AP efficiently.',
    tools: ['query_database', 'optimize_payments', 'handle_dispute']
  }
};

function updatePersonaDesc(persona) {
  var info = personaInfo[persona];
  if (!info) return;
  document.getElementById('desc-title').textContent = info.title;
  document.getElementById('desc-text').textContent = info.desc;
  var toolsDiv = document.getElementById('desc-tools');
  toolsDiv.innerHTML = '';
  for (var i = 0; i < info.tools.length; i++) {
    var span = document.createElement('span');
    span.className = 'tool-tag';
    span.textContent = info.tools[i];
    toolsDiv.appendChild(span);
  }
}

// Persona buttons
document.querySelectorAll('.persona-btn').forEach(function(btn) {
  btn.addEventListener('click', function() {
    if (isStreaming) return;
    document.querySelectorAll('.persona-btn').forEach(function(b) { b.classList.remove('active'); });
    btn.classList.add('active');
    currentPersona = btn.dataset.persona;
    conversationHistory = [];
    updatePersonaDesc(currentPersona);
  });
});

// Trace toggle
document.getElementById('trace-toggle').addEventListener('change', function() {
  if (this.checked) {
    document.body.classList.remove('hide-trace');
  } else {
    document.body.classList.add('hide-trace');
  }
});

// Auto-resize textarea
var input = document.getElementById('msg-input');
input.addEventListener('input', function() {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 120) + 'px';
});

// Enter to send (shift+enter for newline)
input.addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

function askExample(btn) {
  input.value = btn.textContent;
  sendMessage();
}

function escapeHtml(text) {
  var div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

function renderMarkdown(text) {
  var html = escapeHtml(text);
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  html = html.replace(/^---$/gm, '<hr>');
  html = html.replace(/\n/g, '<br>');
  html = html.replace(/((?:<li>.*?<\/li>(?:<br>)?)+)/g, function(match) {
    return '<ul>' + match.replace(/<br>/g, '') + '</ul>';
  });
  return html;
}

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
  var div = document.createElement('div');
  div.className = 'trace-block';

  if (type === 'tool_call') {
    div.innerHTML = '<span class="icon">&#9881;</span><span class="tool-name">' + escapeHtml(content.name) + '</span><span class="trace-text">called</span>';
  } else if (type === 'tool_result') {
    div.innerHTML = '<span class="icon">&#10003;</span><span class="tool-name">' + escapeHtml(content.name) + '</span><span class="trace-text">returned results</span>';
  } else {
    div.innerHTML = '<span class="icon">&#9733;</span><span class="trace-text">' + escapeHtml(String(content)) + '</span>';
  }

  container.appendChild(div);
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

function handleSSELine(line, msg) {
  if (!line.startsWith('data: ')) return;
  var jsonStr = line.substring(6);
  if (!jsonStr || jsonStr.trim() === '') return;

  console.log('[SSE]', jsonStr.substring(0, 200));

  try {
    var event = JSON.parse(jsonStr);
  } catch(e) {
    console.error('[SSE] bad JSON:', e);
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
    addMessage('assistant', event.content);
    var container = document.getElementById('chat-container');
    var stats = document.createElement('div');
    stats.className = 'stats-bar';
    stats.textContent = event.tool_calls + ' tool calls | ' + event.elapsed + 's | ' + event.iterations + ' iterations';
    container.appendChild(stats);
    scrollToBottom();
    conversationHistory.push({role: 'user', content: msg});
    conversationHistory.push({role: 'assistant', content: event.content});
  } else if (event.type === 'done') {
    console.log('[SSE] done');
  }
}

function sendMessage() {
  var msg = input.value.trim();
  if (!msg || isStreaming) return;

  console.log('[Chat] sending:', msg);
  isStreaming = true;
  document.getElementById('send-btn').disabled = true;
  input.value = '';
  input.style.height = 'auto';

  addMessage('user', msg);
  addTypingIndicator();

  var xhr = new XMLHttpRequest();
  xhr.open('POST', '/chat', true);
  xhr.setRequestHeader('Content-Type', 'application/json');

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
    console.log('[XHR] complete, status:', xhr.status);
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
    console.error('[XHR] network error');
    removeTypingIndicator();
    addMessage('assistant', 'Connection error. Is the server running?');
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
