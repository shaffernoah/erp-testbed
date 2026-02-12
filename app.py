"""
LaFrieda ERP Agent Chat Interface

Single-file Flask app with embedded HTML/JS chatbot UI.
Run: python app.py
Open: http://localhost:5001
"""

import os
import sys
import json
import time
import inspect
import logging
from functools import partial

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'), override=True)

from flask import Flask, request, Response, stream_with_context, send_from_directory

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import anthropic
from database.connection import get_session
from agents.tool_registry import Tool, ToolRegistry
from agents.prompts.vendor_ops_agent import SYSTEM_PROMPT as OPS_PROMPT
from agents.prompts.vendor_sales_agent import SYSTEM_PROMPT as SALES_PROMPT
from agents.prompts.restaurant_agent import SYSTEM_PROMPT as RESTAURANT_PROMPT

# Import tool definitions
from agents.tools.query_database import TOOL_DEF as qd_def
from agents.tools.alert_triggers import TOOL_DEF as at_def
from agents.tools.campaign_generator import TOOL_DEF as cg_def
from agents.tools.payment_optimizer import TOOL_DEF as po_def
from agents.tools.reorder_suggestions import TOOL_DEF as rs_def
from agents.tools.dispute_handler import TOOL_DEF as dh_def
from agents.tools.inventory_optimizer import TOOL_DEF as io_def

logging.basicConfig(level=logging.WARNING)

app = Flask(__name__)

# --- Setup ---
client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
session = get_session()
model = os.getenv('LLM_MODEL', 'claude-sonnet-4-20250514')

PERSONAS = {
    "vendor_ops": {"name": "Vendor Operations", "prompt": OPS_PROMPT},
    "vendor_sales": {"name": "Vendor Sales", "prompt": SALES_PROMPT},
    "restaurant": {"name": "Restaurant Buyer", "prompt": RESTAURANT_PROMPT},
}

def build_registry():
    """Build tool registry with session-bound functions."""
    registry = ToolRegistry()
    for td in [qd_def, at_def, cg_def, po_def, rs_def, dh_def, io_def]:
        sig = inspect.signature(td.function)
        if 'session' in sig.parameters:
            def make_bound(fn):
                def bound(**kwargs):
                    return fn(session=session, **kwargs)
                return bound
            tool = Tool(
                name=td.name, description=td.description, parameters=td.parameters,
                function=make_bound(td.function),
                requires_confirmation=td.requires_confirmation, tags=td.tags,
            )
        else:
            tool = td
        registry.register(tool)
    return registry

registry = build_registry()


def run_agent_streaming(user_message, persona_key, conversation_history):
    """Generator that yields SSE events as the agent works."""
    persona = PERSONAS.get(persona_key, PERSONAS["vendor_ops"])
    system_prompt = persona["prompt"]
    tools_payload = registry.get_tools_for_anthropic()

    # Build messages from conversation history + new message
    messages = []
    for msg in conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    max_iterations = 15
    t0 = time.time()
    tool_calls_count = 0

    for iteration in range(max_iterations):
        # Signal iteration start
        yield f"data: {json.dumps({'type': 'thinking', 'content': f'Iteration {iteration + 1}...'})}\n\n"

        response = client.messages.create(
            model=model, max_tokens=4096, temperature=0.2,
            system=system_prompt, messages=messages, tools=tools_payload,
        )

        text_parts = []
        tool_use_blocks = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_use_blocks.append(block)

        # If done (no tool calls), yield the final answer
        if response.stop_reason == "end_turn" or not tool_use_blocks:
            elapsed = round(time.time() - t0, 1)
            final_text = '\n'.join(text_parts)
            yield f"data: {json.dumps({'type': 'answer', 'content': final_text, 'tool_calls': tool_calls_count, 'elapsed': elapsed, 'iterations': iteration + 1})}\n\n"
            yield "data: {\"type\": \"done\"}\n\n"
            return

        # Stream tool call info
        for block in tool_use_blocks:
            args_preview = json.dumps(block.input)
            if len(args_preview) > 300:
                args_preview = args_preview[:300] + '...'
            yield f"data: {json.dumps({'type': 'tool_call', 'name': block.name, 'args': args_preview})}\n\n"

        # If there was thinking text before tool calls, stream it
        for text in text_parts:
            if text.strip():
                yield f"data: {json.dumps({'type': 'thinking', 'content': text})}\n\n"

        # Build assistant message
        assistant_content = []
        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use", "id": block.id,
                    "name": block.name, "input": block.input,
                })
        messages.append({"role": "assistant", "content": assistant_content})

        # Execute tools
        tool_results = []
        for block in tool_use_blocks:
            tool_calls_count += 1
            result = registry.execute(block.name, block.input)
            result_str = json.dumps(result, default=str)

            # Stream a preview of the result
            preview = result_str[:400] + '...' if len(result_str) > 400 else result_str
            yield f"data: {json.dumps({'type': 'tool_result', 'name': block.name, 'preview': preview})}\n\n"

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_str,
            })

        messages.append({"role": "user", "content": tool_results})

    # Max iterations reached
    elapsed = round(time.time() - t0, 1)
    yield f"data: {json.dumps({'type': 'answer', 'content': '(Max iterations reached. The agent may need a more specific question.)', 'tool_calls': tool_calls_count, 'elapsed': elapsed, 'iterations': max_iterations})}\n\n"
    yield "data: {\"type\": \"done\"}\n\n"


# --- Routes ---

@app.route('/')
def index():
    return HTML_PAGE

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message', '')
    persona = data.get('persona', 'vendor_ops')
    history = data.get('history', [])

    return Response(
        stream_with_context(run_agent_streaming(user_message, persona, history)),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


# --- HTML/JS/CSS (all inline) ---

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LaFrieda ERP Agent</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: #0f1117;
    color: #e4e4e7;
    height: 100vh;
    display: flex;
    flex-direction: column;
  }
  header {
    background: #18181b;
    border-bottom: 1px solid #27272a;
    padding: 12px 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    flex-shrink: 0;
  }
  header h1 {
    font-size: 16px;
    font-weight: 600;
    color: #fafafa;
  }
  header .subtitle {
    font-size: 12px;
    color: #71717a;
  }
  .persona-select {
    margin-left: auto;
    display: flex;
    gap: 6px;
  }
  .persona-btn {
    padding: 5px 12px;
    border-radius: 6px;
    border: 1px solid #3f3f46;
    background: #27272a;
    color: #a1a1aa;
    font-size: 12px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .persona-btn:hover { border-color: #52525b; color: #e4e4e7; }
  .persona-btn.active {
    background: #dc2626;
    border-color: #dc2626;
    color: white;
  }
  .header-right {
    margin-left: auto;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 8px;
  }
  .header-controls {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .trace-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: #71717a;
    cursor: pointer;
    user-select: none;
  }
  .trace-toggle input {
    accent-color: #dc2626;
    cursor: pointer;
  }
  .persona-desc {
    background: #1a1a2e;
    border: 1px solid #27272a;
    border-radius: 8px;
    padding: 10px 14px;
    margin: 0 20px 0 20px;
    font-size: 12px;
    color: #a1a1aa;
    line-height: 1.5;
    flex-shrink: 0;
  }
  .persona-desc .desc-title {
    color: #e4e4e7;
    font-weight: 600;
    font-size: 13px;
    margin-bottom: 4px;
  }
  .persona-desc .desc-tools {
    margin-top: 6px;
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .persona-desc .tool-tag {
    background: #27272a;
    border: 1px solid #3f3f46;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    color: #a78bfa;
  }
  #chat-container {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  .message {
    max-width: 85%;
    padding: 12px 16px;
    border-radius: 12px;
    font-size: 14px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
  .message.user {
    align-self: flex-end;
    background: #dc2626;
    color: white;
    border-bottom-right-radius: 4px;
  }
  .message.assistant {
    align-self: flex-start;
    background: #27272a;
    border: 1px solid #3f3f46;
    border-bottom-left-radius: 4px;
  }
  .message.assistant .md-content h1,
  .message.assistant .md-content h2,
  .message.assistant .md-content h3 {
    margin-top: 12px;
    margin-bottom: 6px;
    color: #fafafa;
  }
  .message.assistant .md-content h2 { font-size: 15px; }
  .message.assistant .md-content h3 { font-size: 14px; }
  .message.assistant .md-content ul,
  .message.assistant .md-content ol {
    padding-left: 20px;
    margin: 4px 0;
  }
  .message.assistant .md-content strong { color: #fafafa; }
  .message.assistant .md-content code {
    background: #18181b;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 13px;
  }
  .message.assistant .md-content table {
    border-collapse: collapse;
    margin: 8px 0;
    font-size: 13px;
    width: 100%;
  }
  .message.assistant .md-content th,
  .message.assistant .md-content td {
    border: 1px solid #3f3f46;
    padding: 4px 8px;
    text-align: left;
  }
  .message.assistant .md-content th { background: #18181b; }
  .trace-block {
    align-self: flex-start;
    max-width: 85%;
    font-size: 12px;
    color: #71717a;
    padding: 6px 12px;
    background: #18181b;
    border-radius: 8px;
    border: 1px solid #27272a;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .trace-block .icon { font-size: 14px; }
  .trace-block .tool-name { color: #a78bfa; font-weight: 600; }
  .trace-block .trace-text { color: #71717a; }
  body.hide-trace .trace-block { display: none; }
  .stats-bar {
    font-size: 11px;
    color: #52525b;
    align-self: flex-start;
    padding: 2px 0 0 4px;
  }
  #input-area {
    background: #18181b;
    border-top: 1px solid #27272a;
    padding: 16px 20px;
    display: flex;
    gap: 10px;
    flex-shrink: 0;
  }
  #msg-input {
    flex: 1;
    background: #27272a;
    border: 1px solid #3f3f46;
    border-radius: 10px;
    padding: 10px 14px;
    color: #fafafa;
    font-size: 14px;
    font-family: inherit;
    resize: none;
    outline: none;
    min-height: 42px;
    max-height: 120px;
  }
  #msg-input:focus { border-color: #dc2626; }
  #msg-input::placeholder { color: #52525b; }
  #send-btn {
    background: #dc2626;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s;
    align-self: flex-end;
  }
  #send-btn:hover { background: #b91c1c; }
  #send-btn:disabled { background: #52525b; cursor: not-allowed; }
  .typing-indicator {
    align-self: flex-start;
    display: flex;
    gap: 4px;
    padding: 12px 16px;
  }
  .typing-indicator span {
    width: 8px; height: 8px;
    background: #52525b;
    border-radius: 50%;
    animation: bounce 1.4s infinite ease-in-out both;
  }
  .typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
  .typing-indicator span:nth-child(2) { animation-delay: -0.16s; }
  @keyframes bounce {
    0%, 80%, 100% { transform: scale(0); }
    40% { transform: scale(1); }
  }
  .welcome {
    text-align: center;
    padding: 60px 20px;
    color: #52525b;
  }
  .welcome h2 { color: #a1a1aa; font-size: 20px; margin-bottom: 8px; }
  .welcome p { font-size: 13px; max-width: 500px; margin: 0 auto 16px; line-height: 1.5; }
  .welcome .examples {
    display: flex;
    flex-direction: column;
    gap: 6px;
    align-items: center;
  }
  .welcome .example-btn {
    background: #27272a;
    border: 1px solid #3f3f46;
    color: #a1a1aa;
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.15s;
    max-width: 500px;
    width: 100%;
    text-align: left;
  }
  .welcome .example-btn:hover {
    border-color: #dc2626;
    color: #e4e4e7;
  }
</style>
</head>
<body>

<header>
  <div>
    <h1>Pat LaFrieda ERP Agent</h1>
    <div class="subtitle">AI-powered operations & sales intelligence</div>
  </div>
  <div class="header-right">
    <div class="persona-select">
      <button class="persona-btn active" data-persona="vendor_ops">Operations</button>
      <button class="persona-btn" data-persona="vendor_sales">Sales</button>
      <button class="persona-btn" data-persona="restaurant">Restaurant</button>
    </div>
    <div class="header-controls">
      <label class="trace-toggle">
        <input type="checkbox" id="trace-toggle" checked> Show agent trace
      </label>
    </div>
  </div>
</header>

<div class="persona-desc" id="persona-desc">
  <div class="desc-title" id="desc-title">Vendor Operations Agent</div>
  <div id="desc-text">Food safety, spoilage prevention, inventory optimization, replenishment planning, and operational alerting. Monitors lot expirations, temperature compliance, FIFO discipline, and warehouse zone transfers.</div>
  <div class="desc-tools" id="desc-tools">
    <span class="tool-tag">query_database</span>
    <span class="tool-tag">check_alerts</span>
    <span class="tool-tag">optimize_inventory</span>
    <span class="tool-tag">get_reorder_suggestions</span>
    <span class="tool-tag">generate_campaign</span>
    <span class="tool-tag">handle_dispute</span>
    <span class="tool-tag">optimize_payments</span>
  </div>
</div>

<div id="chat-container">
  <div class="welcome" id="welcome">
    <h2>LaFrieda ERP Agent</h2>
    <p>Ask questions about inventory, customers, sales, spoilage risk, campaigns, and more. The agent will query the database and use tools to answer.</p>
    <div class="examples">
      <button class="example-btn" onclick="askExample(this)">What inventory is at risk of expiring in the next 7 days?</button>
      <button class="example-btn" onclick="askExample(this)">Which Cari-enrolled accounts show signs of churn? Build a win-back campaign.</button>
      <button class="example-btn" onclick="askExample(this)">Give me a daily operational briefing with alerts and recommended actions.</button>
      <button class="example-btn" onclick="askExample(this)">What are our top 10 customers by revenue and how is their payment health?</button>
    </div>
  </div>
</div>

<div id="input-area">
  <textarea id="msg-input" placeholder="Ask the agent anything..." rows="1"></textarea>
  <button id="send-btn" onclick="sendMessage()">Send</button>
</div>

<script src="/static/app.js"></script>

</body>
</html>
"""


if __name__ == '__main__':
    print("=" * 50)
    print("  LaFrieda ERP Agent Chat")
    print(f"  Model: {model}")
    print(f"  Tools: {registry.tool_names}")
    print(f"  Open: http://localhost:5001")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)
