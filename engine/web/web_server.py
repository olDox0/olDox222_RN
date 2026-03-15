# -*- coding: utf-8 -*-
"""
ORN — Web Interface Server (Apolo)
Servidor HTTP local que serve a interface web e faz proxy para o SiCDox Server.

Porta: 8372 (web) -> 8371 (inferencia)
Uso:
  orn-web start          inicia e abre o browser
  orn-web start --no-browser  inicia sem abrir browser
  orn-web stop           para o servidor

Mudancas v0.3:
  - Auto-search two-pass integrado no POST /ask
  - Response JSON inclui source e source_url
  - renderMarkdown: indentacao e tabs preservados
  - Badge de fonte exibido na interface

OSL-18: stdlib apenas (http.server, json, threading, webbrowser, socket).
OSL-15: Erros de proxy nao derrubam o servidor web.
God: Apolo — da forma e clareza ao pensamento do Hefesto.
"""

from __future__ import annotations

import json
import os
import socket
# [DOX-UNUSED] import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

WEB_PORT   = 8372
INFER_PORT = 8371
HOST       = "127.0.0.1"
PID_FILE   = Path("web_server.pid")


# ---------------------------------------------------------------------------
# HTML da interface
# ---------------------------------------------------------------------------

HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ORN — AI CLI Interface</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@400;700;800&display=swap');

  :root {
    --bg:        #0f0d0f;
    --surface:   #19171a;
    --surface2:  #2f2e30;
    --border:    #5e5c5e;
    --accent:    #26bc5f;
    --accent2:   #197b3f;
    --success:   #3dd68c;
    --warn:      #f5a623;
    --text:      #FF6700;
    --text-dim:  #ffbe78;
    --code-bg:   #001404;
    --code-text: #a8e6a8;
    --radius:    13px;
    --mono:      'JetBrains Mono', monospace;
    --sans:      'Syne', sans-serif;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* ── HEADER ── */
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 15px 25px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }

  .logo { display: flex; align-items: center; gap: 25px; }

  .logo-mark {
    width: 106px; height: 36px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-family: var(--mono);
    font-size: 14px; font-weight: 600;
    color: #fff; letter-spacing: -1px;
  }

  .logo-text { font-size: 18px; font-weight: 800; letter-spacing: -0.5px; }
  .logo-sub  { font-size: 11px; color: var(--text-dim); font-family: var(--mono); }

  .server-status {
    display: flex; align-items: center; gap: 8px;
    font-family: var(--mono); font-size: 12px;
    color: var(--text-dim);
  }

  .status-dot {
    width: 12px; height: 8px; border-radius: 50%;
    background: var(--text-dim);
    transition: background 0.3s;
  }
  .status-dot.online  { background: var(--success); box-shadow: 0 0 6px var(--success); }
  .status-dot.offline { background: #ef4444; }

  /* ── CHAT AREA ── */
  #chat {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    scroll-behavior: smooth;
  }

  #chat::-webkit-scrollbar { width: 4px; }
  #chat::-webkit-scrollbar-track { background: transparent; }
  #chat::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

  .msg {
    display: flex;
    gap: 13px;
    animation: fadeUp 0.25s ease;
    max-width: 860px;
    width: 80%;
  }

  .msg.user  { align-self: flex-end; flex-direction: row-reverse; }
  .msg.model { align-self: flex-start; }

  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  .avatar {
    width: 32px; height: 32px; border-radius: 8px;
    flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-family: var(--mono); font-size: 11px; font-weight: 600;
  }

  .msg.user  .avatar { background: linear-gradient(135deg, var(--accent), var(--accent2)); color: #fff; }
  .msg.model .avatar { background: var(--surface2); color: var(--accent); border: 1px solid var(--border); }

  .bubble {
    padding: 12px 16px;
    border-radius: var(--radius);
    font-size: 14px;
    line-height: 1.7;
    max-width: calc(100% - 44px);
  }

  .msg.user  .bubble {
    background: linear-gradient(135deg, #1e3a5f, #1a2d4f);
    border: 1px solid #2a4a7f;
    color: var(--text);
    border-bottom-right-radius: 4px;
  }

  .msg.model .bubble {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    border-bottom-left-radius: 4px;
  }

  /* ── META + SOURCE ── */
  .bubble .meta {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--text-dim);
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .source-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: rgba(38, 188, 95, 0.12);
    border: 1px solid rgba(38, 188, 95, 0.35);
    border-radius: 4px;
    padding: 1px 7px;
    font-family: var(--mono);
    font-size: 10px;
    color: var(--success);
    text-decoration: none;
    transition: background 0.2s;
  }
  .source-badge:hover { background: rgba(38, 188, 95, 0.22); }
  .source-badge::before { content: "⬡"; font-size: 9px; }

  /* ── CODE BLOCKS ── */
  .bubble pre {
    background: var(--code-bg);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    border-radius: 8px;
    padding: 14px 16px;
    margin: 10px 0;
    overflow-x: auto;
    position: relative;
  }

  .bubble pre::-webkit-scrollbar { height: 3px; }
  .bubble pre::-webkit-scrollbar-thumb { background: var(--border); }

  .bubble code {
    font-family: var(--mono);
    font-size: 13px;
    line-height: 1.75;
    color: var(--code-text);
    /* CRÍTICO: preserva tabs e espaços de indentação */
    white-space: pre;
    tab-size: 4;
    -moz-tab-size: 4;
  }

  .bubble p > code {
    background: var(--code-bg);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 12px;
    color: var(--accent);
    border: 1px solid var(--border);
    white-space: pre;
  }

  .lang-tag {
    position: absolute;
    top: 8px; right: 10px;
    font-family: var(--mono);
    font-size: 10px;
    color: var(--text-dim);
    background: var(--surface2);
    padding: 2px 8px;
    border-radius: 4px;
    border: 1px solid var(--border);
  }

  /* ── THINKING INDICATOR ── */
  .thinking-msg .bubble {
    display: flex; align-items: center; gap: 10px;
    color: var(--text-dim);
    font-family: var(--mono); font-size: 13px;
    padding: 14px 16px;
  }

  .dots span {
    display: inline-block;
    width: 5px; height: 5px;
    background: var(--accent);
    border-radius: 50%;
    animation: pulse 1.2s infinite;
  }
  .dots span:nth-child(2) { animation-delay: 0.2s; }
  .dots span:nth-child(3) { animation-delay: 0.4s; }

  @keyframes pulse {
    0%,80%,100% { opacity: 0.2; transform: scale(0.8); }
    40%          { opacity: 1;   transform: scale(1);   }
  }

  /* ── EMPTY STATE ── */
  .empty-state {
    flex: 1;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    gap: 12px; color: var(--text-dim);
    text-align: center;
  }

  .empty-state .big { font-size: 48px; }
  .empty-state h2   { font-size: 20px; font-weight: 700; color: var(--text); }
  .empty-state p    { font-size: 13px; font-family: var(--mono); }

  .suggestions {
    display: flex; flex-wrap: wrap; gap: 8px;
    justify-content: center; margin-top: 8px;
  }

  .sug-btn {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text-dim);
    font-family: var(--mono); font-size: 12px;
    padding: 6px 14px; border-radius: 20px;
    cursor: pointer; transition: all 0.2s;
  }
  .sug-btn:hover {
    border-color: var(--accent); color: var(--accent);
    background: rgba(38,188,95,0.05);
  }

  /* ── INPUT AREA ── */
  footer {
    background: var(--surface);
    border-top: 1px solid var(--border);
    padding: 16px 24px;
    flex-shrink: 0;
  }

  .token-row {
    display: flex; align-items: center; gap: 12px;
    margin-bottom: 12px;
    font-family: var(--mono); font-size: 12px; color: var(--text-dim);
  }

  .token-row label { white-space: nowrap; }

  #tokenSlider {
    flex: 1; -webkit-appearance: none;
    height: 3px; background: var(--border);
    border-radius: 3px; outline: none;
  }

  #tokenSlider::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 14px; height: 14px;
    background: var(--accent); border-radius: 50%;
    cursor: pointer; transition: background 0.2s;
  }
  #tokenSlider::-webkit-slider-thumb:hover { background: var(--accent2); }

  #tokenVal { min-width: 38px; text-align: right; color: var(--accent); font-weight: 600; }

  .input-row { display: flex; gap: 10px; align-items: flex-end; }

  #promptInput {
    flex: 1;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    font-family: var(--sans); font-size: 14px;
    padding: 12px 16px;
    resize: none;
    height: 48px; min-height: 48px; max-height: 200px;
    overflow-y: auto; outline: none;
    transition: border-color 0.2s;
    line-height: 1.5;
  }

  #promptInput:focus { border-color: var(--accent); }
  #promptInput::placeholder { color: var(--text-dim); }

  #sendBtn {
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border: none; border-radius: var(--radius);
    color: #fff; font-family: var(--sans);
    font-size: 14px; font-weight: 700;
    padding: 0 22px; height: 48px;
    cursor: pointer; transition: opacity 0.2s, transform 0.1s;
    white-space: nowrap; flex-shrink: 0;
  }
  #sendBtn:hover   { opacity: 0.9; }
  #sendBtn:active  { transform: scale(0.97); }
  #sendBtn:disabled { opacity: 0.4; cursor: not-allowed; }

  .hint {
    margin-top: 8px;
    font-family: var(--mono); font-size: 11px; color: var(--text-dim);
    text-align: center;
  }

  /* ── TIPOGRAFIA DO BUBBLE ── */
  .bubble h1, .bubble h2, .bubble h3,
  .bubble h4, .bubble h5, .bubble h6 {
    margin: 10px 0 4px 0;
    font-family: var(--sans); color: var(--text); font-weight: 700;
  }
  .bubble h3 { font-size: 14px; color: var(--accent); }
  .bubble h2 { font-size: 15px; }
  .bubble h1 { font-size: 16px; }

  .bubble p {
    margin: 4px 0; line-height: 1.75; font-size: 14px;
  }

  .bubble ul { padding-left: 20px; margin: 6px 0; }
  .bubble li { margin: 2px 0; line-height: 1.6; }
</style>
</head>
<body>

<header>
  <div class="logo">
    <div class="logo-mark">ORN</div>
    <div>
      <div class="logo-text">ORN</div>
      <div class="logo-sub">Qwen2.5-Coder · local · N2808</div>
    </div>
  </div>
  <div class="server-status">
    <div class="status-dot" id="dot"></div>
    <span id="statusText">verificando...</span>
  </div>
</header>

<div id="chat">
  <div class="empty-state" id="emptyState">
    <div class="big">⬡</div>
    <h2>ORN pronto</h2>
    <p>Qwen2.5-Coder · Q4_K_M · SSE4.2 · N2808</p>
    <div class="suggestions">
      <button class="sug-btn" onclick="usePrompt('bubble sort em C')">bubble sort em C</button>
      <button class="sug-btn" onclick="usePrompt('função recursiva em Python')">função recursiva Python</button>
      <button class="sug-btn" onclick="usePrompt('o que é KV-cache em LLMs')">o que é KV-cache</button>
      <button class="sug-btn" onclick="usePrompt('script batch para listar arquivos .py')">batch listar .py</button>
    </div>
  </div>
</div>

<footer>
  <div class="token-row">
    <label for="tokenSlider">tokens</label>
    <input type="range" id="tokenSlider" min="32" max="512" step="32" value="128">
    <span id="tokenVal">128</span>
  </div>
  <div class="input-row">
    <textarea id="promptInput" rows="1"
      placeholder="Pergunte ao ORN... (Enter para enviar, Shift+Enter para nova linha)"></textarea>
    <button id="sendBtn" onclick="sendPrompt()">Enviar</button>
  </div>
  <div class="hint">orn-server · 127.0.0.1:8371 · ~1.4 t/s</div>
</footer>

<script>
const chat      = document.getElementById('chat');
const empty     = document.getElementById('emptyState');
const input     = document.getElementById('promptInput');
const sendBtn   = document.getElementById('sendBtn');
const slider    = document.getElementById('tokenSlider');
const tokenVal  = document.getElementById('tokenVal');
const dot       = document.getElementById('dot');
const statusTxt = document.getElementById('statusText');

let busy = false;

// ── Token slider ──────────────────────────────────────────────
slider.addEventListener('input', () => tokenVal.textContent = slider.value);

// ── Auto-resize textarea ──────────────────────────────────────
function resizeInput() {
  input.style.height = '48px';
  input.style.height = Math.min(input.scrollHeight, 200) + 'px';
}
input.addEventListener('input', resizeInput);
input.addEventListener('keyup', resizeInput);

input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!busy) sendPrompt();
  }
});

// ── Suggestions ───────────────────────────────────────────────
function usePrompt(text) {
  input.value = text;
  input.dispatchEvent(new Event('input'));
  input.focus();
}

// ── Server status polling ─────────────────────────────────────
async function checkStatus() {
  try {
    const r = await fetch('/status', { signal: AbortSignal.timeout(2000) });
    const s = await r.json();
    dot.className = 'status-dot online';
    const up = s.uptime_s || 0;
    const h  = String(Math.floor(up / 3600)).padStart(2, '0');
    const m  = String(Math.floor((up % 3600) / 60)).padStart(2, '0');
    const sc = String(Math.floor(up % 60)).padStart(2, '0');
    statusTxt.textContent = `online · ${h}:${m}:${sc} · ${s.requests || 0} req`;
  } catch {
    dot.className = 'status-dot offline';
    statusTxt.textContent = 'servidor offline';
  }
}
checkStatus();
setInterval(checkStatus, 10000);

// ── Markdown / code highlight ─────────────────────────────────
function escCode(s) {
  // Preserva indentação: substitui apenas caracteres HTML especiais,
  // mantendo tabs (\t), espaços e quebras de linha intactos.
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function escHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function renderMarkdown(text) {
  const blocks = [];

  // 1. Extrai blocos de código ``` ... ```
  // CRÍTICO: não aplica trim() no conteúdo — preserva indentação original
  text = text.replace(/```(\w*)[ \t]*\r?\n([\s\S]*?)```/g, (_, lang, code) => {
    // Remove apenas a última quebra de linha (se houver), sem tocar na indentação
    const codeClean = code.replace(/\n$/, '');
    const tag = lang ? `<span class="lang-tag">${escHtml(lang)}</span>` : '';
    const idx = blocks.length;
    blocks.push(`<pre>${tag}<code>${escCode(codeClean)}</code></pre>`);
    return `\x00BLOCK${idx}\x00`;
  });

  // 2. Escapa HTML do texto restante (fora dos blocos)
  text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // 3. Headers markdown
  text = text.replace(/^#{6}\s+(.+)$/gm, '<h6>$1</h6>');
  text = text.replace(/^#{5}\s+(.+)$/gm, '<h5>$1</h5>');
  text = text.replace(/^#{4}\s+(.+)$/gm, '<h4>$1</h4>');
  text = text.replace(/^#{3}\s+(.+)$/gm, '<h3>$1</h3>');
  text = text.replace(/^#{2}\s+(.+)$/gm, '<h2>$1</h2>');
  text = text.replace(/^#\s+(.+)$/gm,    '<h1>$1</h1>');

  // 4. Negrito e itálico
  text = text.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/\*([^*\n]+)\*/g,     '<em>$1</em>');

  // 5. Código inline
  text = text.replace(/`([^`\n]+)`/g, '<code>$1</code>');

  // 6. Listas
  text = text.replace(/^[-*]\s+(.+)$/gm, '<li>$1</li>');
  text = text.replace(/(<li>[\s\S]*?<\/li>\n?)+/g, m => `<ul>${m}</ul>`);

  // 7. Parágrafos (não envolve headers/ul/pre em <p>)
  const lines = text.split('\n');
  let html = '', inPara = false;
  for (const line of lines) {
    const trimmed = line.trim();
    const isBlock = /^<(h[1-6]|ul|li|pre|\x00BLOCK)/.test(trimmed) || trimmed === '';
    if (isBlock) {
      if (inPara) { html += '</p>'; inPara = false; }
      if (trimmed !== '') html += trimmed + '\n';
    } else {
      if (!inPara) { html += '<p>'; inPara = true; }
      else html += '<br>';
      html += trimmed;
    }
  }
  if (inPara) html += '</p>';

  // 8. Restaura blocos de código
  html = html.replace(/\x00BLOCK(\d+)\x00/g, (_, i) => blocks[+i]);

  return html;
}

// ── Append message ────────────────────────────────────────────
function appendMsg(role, html, meta, source, sourceUrl) {
  if (empty.style.display !== 'none') empty.style.display = 'none';

  const div = document.createElement('div');
  div.className = `msg ${role}`;

  const av = document.createElement('div');
  av.className = 'avatar';
  av.textContent = role === 'user' ? 'EU' : 'ORN';

  const bub = document.createElement('div');
  bub.className = 'bubble';
  bub.innerHTML = html;

  if (meta || source) {
    const m = document.createElement('div');
    m.className = 'meta';
    if (meta) {
      const t = document.createElement('span');
      t.textContent = meta;
      m.appendChild(t);
    }
    // Badge de fonte — aparece quando source está presente
    if (source) {
      const badge = document.createElement('a');
      badge.className = 'source-badge';
      badge.textContent = source;
      badge.title = sourceUrl || source;
      if (sourceUrl) {
        badge.href   = sourceUrl;
        badge.target = '_blank';
        badge.rel    = 'noopener noreferrer';
      }
      m.appendChild(badge);
    }
    bub.appendChild(m);
  }

  div.appendChild(av);
  div.appendChild(bub);
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function appendThinking() {
  const div = document.createElement('div');
  div.className = 'msg model thinking-msg';
  div.innerHTML = `
    <div class="avatar">ORN</div>
    <div class="bubble">
      <div class="dots"><span></span><span></span><span></span></div>
      <span>processando...</span>
    </div>`;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

// ── Send ──────────────────────────────────────────────────────
async function sendPrompt() {
  const prompt = input.value.trim();
  if (!prompt || busy) return;

  busy = true;
  sendBtn.disabled = true;
  input.value = '';
  input.style.height = 'auto';

  appendMsg('user', escHtml(prompt));

  const tokens   = parseInt(slider.value);
  const thinking = appendThinking();

  try {
    const res = await fetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, max_tokens: tokens })
    });
    const data = await res.json();
    thinking.remove();

    if (data.error) {
      appendMsg('model', `<span style="color:#ef4444">⚠ ${escHtml(data.error)}</span>`);
    } else {
      const meta = `${data.elapsed_s}s · ${tokens} tokens · servidor`;
      appendMsg('model', renderMarkdown(data.output), meta,
                data.source || null, data.source_url || null);
    }
  } catch (e) {
    thinking.remove();
    appendMsg('model', `<span style="color:#ef4444">⚠ Erro de conexão: ${e.message}</span>`);
  }

  busy = false;
  sendBtn.disabled = false;
  input.focus();
}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Auto-search two-pass (inline — sem import do engine para manter stdlib)
# ---------------------------------------------------------------------------

def _decide_search(prompt: str) -> str | None:
    """1ª pass: pergunta ao modelo se precisa de busca externa.

    Retorna termo de busca ou None.
    OSL-4: função curta, uma responsabilidade.
    """
    decision_prompt = (
        "Você é um motor de decisão de busca.\n"
        "Leia a pergunta e decida:\n"
        "- Se precisar de dados externos, fatos específicos ou pesquisa: responda APENAS com BUSCA:<termo>\n"
        "- Se for conhecimento geral de programação: responda APENAS com NO\n\n"
        "Regras:\n"
        "- BUSCA:<termo> deve ter no máximo 3 palavras\n"
        "- Nenhuma explicação extra\n\n"
        f"Pergunta: {prompt.strip()}"
    )
    resp = _query_infer_raw(
        json.dumps({"prompt": decision_prompt, "max_tokens": 20}).encode() + b"\n"
    )
    if not resp or resp.get("error"):
        return None
    return _parse_search_decision(resp.get("output", ""))


def _parse_search_decision(text: str) -> str | None:
    """Parse defensivo da resposta de decisão.

    OSL-5.1: nunca levanta exceção — retorna None em caso de dúvida.
    """
    if not text:
        return None
    normalized = text.strip().lower()
    # Aceitar as traduções prováveis do Qwen:
    for prefix in ("search:", "busca:", "pesquisar:", "buscar:", "pesquisa:"):
        if normalized.startswith(prefix):
            term = text.strip()[len(prefix):].strip()
            if not term or len(term.split()) > 5:
                return None
            return term
    return None


def _run_crawler(query: str) -> tuple[str, str, str]:
    """Executa o crawler e retorna (context_block, source, source_url).

    Retorna ('', '', '') se falhar.
    OSL-15: falha não propaga exceção.
    """
    try:
        from engine.tools.crawler import OrnCrawler  # noqa: PLC0415
        result = OrnCrawler().search(query, source="auto")
        if result.ok:
            return result.to_prompt_block(), result.source, result.url
    except Exception as e:
        import traceback
        print(f"\033[31m ■ Erro: {e}")
        traceback.print_tb(e.__traceback__)
        pass
    return "", "", ""


# ---------------------------------------------------------------------------
# Handler HTTP
# ---------------------------------------------------------------------------

class ORNHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        try:
            self.send_response(code)
            if ctype:
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", HTML.encode("utf-8"))
        elif self.path == "/status":
            resp = _query_infer_raw(b"STATUS\n")
            if resp is None:
                resp = {"status": "offline", "error": "orn-server nao encontrado"}
            self._send(200, "application/json", json.dumps(resp).encode())
        elif self.path == "/favicon.ico":
            self._send(204, "", b"")
        else:
            self._send(404, "", b"")

    def do_POST(self):
        if self.path != "/ask":
            self._send(404, "", b"")
            return

        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            req = json.loads(body)
        except Exception:
            req = {}

        prompt     = str(req.get("prompt", "")).strip()
        max_tokens = max(1, min(int(req.get("max_tokens", 128)), 2048))

        if not prompt:
            resp = {"output": "", "elapsed_s": 0, "error": "prompt vazio",
                    "source": None, "source_url": None}
            self._send(200, "application/json",
                       json.dumps(resp, ensure_ascii=False).encode())
            return

        # ---------------------------------------------------------------
        # TWO-PASS AUTÔNOMO
        # 1ª pass: decide se precisa de busca
        # ---------------------------------------------------------------
        ctx_block  = ""
        source     = None
        source_url = None

        search_term = _decide_search(prompt)
        if search_term:
            ctx_block, source, source_url = _run_crawler(search_term)
            # Se crawler falhou — source fica None, continua sem contexto

        # Monta prompt final
        if ctx_block:
            full_prompt = ctx_block + "\n[TASK]\n" + prompt
        else:
            full_prompt = prompt

        # ---------------------------------------------------------------
        # 2ª pass: inferência com contexto
        # ---------------------------------------------------------------
        payload = (json.dumps({
            "prompt":     full_prompt,
            "max_tokens": max_tokens
        }) + "\n").encode()

        infer_resp = _query_infer_raw(payload)

        if infer_resp is None:
            resp = {"output": "", "elapsed_s": 0,
                    "error": "orn-server offline. Execute: orn-server start",
                    "source": None, "source_url": None}
        else:
            resp = {
                "output":     infer_resp.get("output", ""),
                "elapsed_s":  infer_resp.get("elapsed_s", 0),
                "error":      infer_resp.get("error"),
                "source":     source or None,
                "source_url": source_url or None,
            }

        out = json.dumps(resp, ensure_ascii=False).encode()
        self._send(200, "application/json", out)


# ---------------------------------------------------------------------------
# Socket helper — reutilizado por handler e funções inline
# ---------------------------------------------------------------------------

def _query_infer_raw(payload: bytes) -> dict | None:
    """Envia payload para o SiCDox Server e retorna dict ou None."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3.0)
            s.connect((HOST, INFER_PORT))
            s.settimeout(None)
            s.sendall(payload)
            data = b""
            while True:
                chunk = s.recv(1048576)  # 1 MB
                if not chunk:
                    break
                data += chunk
                if data.endswith(b"\n"):
                    break
        return json.loads(data.decode("utf-8").strip())
    except Exception: return None

# ---------------------------------------------------------------------------
# WebCLI
# ---------------------------------------------------------------------------

class WebCLI:

    def run(self, args: list[str]) -> None:
        if not args or args[0] == "start":
            no_browser = "--no-browser" in args
            self._start(open_browser=not no_browser)
        elif args[0] == "stop":
            self._stop()
        else:
            print("orn-web start [--no-browser]")
            print("orn-web stop")

    def _start(self, open_browser: bool = True) -> None:
        url = f"http://{HOST}:{WEB_PORT}"
        srv = HTTPServer((HOST, WEB_PORT), ORNHandler)
        srv.socket.settimeout(1.0)
        PID_FILE.write_text(str(os.getpid()))

        print(f"[WEB] Interface ORN em: {url}", flush=True)
        print(f"[WEB] PID={os.getpid()}  Ctrl+C para parar", flush=True)

        if open_browser:
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()

        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\n[WEB] Encerrando...", flush=True)
        finally:
            srv.server_close()
            PID_FILE.unlink(missing_ok=True)

    def _stop(self) -> None:
        if not PID_FILE.exists():
            print("[WEB] Nenhum servidor ativo.")
            return
        pid = int(PID_FILE.read_text().strip())
        try:
            import signal
            os.kill(pid, signal.SIGTERM)
            PID_FILE.unlink(missing_ok=True)
            print(f"[WEB] Encerrado (PID {pid}).")
        except Exception as e:
            import traceback
            print(f"[WEB] Erro: {e}")
            print(f"\033[31m ■ Erro: {e}")
            traceback.print_tb(e.__traceback__)