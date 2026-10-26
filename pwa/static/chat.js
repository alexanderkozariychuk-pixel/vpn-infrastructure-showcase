/*
 * chat.js — the support assistant widget, on the landing page and in the
 * account. Talks to /api/public/chat (api/chat.py), which answers from
 * pwa/support/knowledge.md only.
 *
 * Self-contained: its own styles (with the site's colours as fallbacks), its
 * own DOM, nothing it needs from the page. Shows nothing unless the server
 * says the chat is on. The dialogue lives in this tab (sessionStorage) and is
 * sent along with each question; the server keeps none of it.
 */
(function () {
  'use strict';
  if (window.__sovChat) return;
  window.__sovChat = true;

  const KEY = 'sov_chat';
  const MAX_SENT = 12;

  const lang = (() => {
    try { const l = localStorage.getItem('sov_lang'); if (l === 'en' || l === 'ru') return l; } catch (e) {}
    return (document.documentElement.lang || 'ru').startsWith('en') ? 'en' : 'ru';
  })();

  const T = {
    ru: {
      open: 'Помощь', title: 'Помощник Sovereign', sub: 'ИИ-ассистент · отвечает по базе знаний',
      hello: 'Здравствуйте! Я помогу с подключением, тарифами и личным кабинетом. Что случилось?',
      placeholder: 'Ваш вопрос…', send: 'Отправить', close: 'Закрыть', reset: 'Начать заново',
      chips: ['Как подключиться?', 'Тарифы и цены', 'Не подключается', 'Пригласить друга'],
      note: 'Ответы даёт ИИ и могут быть неточны. Не отправляйте файлы подключения и пароли.',
      human: 'Живая поддержка', thinking: 'Пишет…',
      busy: 'Слишком много сообщений. Попробуйте через {m} мин.',
      down: 'Помощник сейчас недоступен. Напишите в поддержку — ответим в течение рабочего дня.',
    },
    en: {
      open: 'Help', title: 'Sovereign assistant', sub: 'AI assistant · answers from our help base',
      hello: 'Hi! I can help with connecting, plans and your account. What happened?',
      placeholder: 'Your question…', send: 'Send', close: 'Close', reset: 'Start over',
      chips: ['How do I connect?', 'Plans and prices', 'It won\'t connect', 'Invite a friend'],
      note: 'Answers come from an AI and may be inaccurate. Never send connection files or passwords.',
      human: 'Human support', thinking: 'Typing…',
      busy: 'Too many messages. Try again in {m} min.',
      down: 'The assistant is unavailable right now. Please contact support — we reply within a working day.',
    },
  }[lang];

  const SUPPORT = 'mailto:sovrn.support@gmail.com';

  function load() {
    try { return JSON.parse(sessionStorage.getItem(KEY) || '[]').filter(m => m && m.role && m.content); }
    catch (e) { return []; }
  }
  function save(h) {
    try { sessionStorage.setItem(KEY, JSON.stringify(h.slice(-40))); } catch (e) {}
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }
  // Plain text in, a little structure out: line breaks, **bold**, and links
  // to our own pages, the channel and the support address — nothing else.
  function render(text) {
    let h = esc(text);
    h = h.replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>');
    h = h.replace(/(https?:\/\/)?((?:sov3r3ign\.com|t\.me\/sov3r3ign_net)[^\s<,)]*)/g, (m, p, rest) => {
      const url = 'https://' + rest.replace(/[.;:]+$/, '');
      return `<a href="${url}" target="_blank" rel="noopener">${esc(rest)}</a>`;
    });
    h = h.replace(/sovrn\.support@gmail\.com/g, '<a href="mailto:sovrn.support@gmail.com">sovrn.support@gmail.com</a>');
    return h.replace(/\n/g, '<br>');
  }

  const css = `
  .sc-btn{position:fixed;right:20px;bottom:20px;z-index:900;display:flex;align-items:center;gap:8px;
    padding:12px 16px;border:1px solid var(--accent,#00d4ff);background:var(--bg-2,#0d1318);color:var(--text-bright,#e8f4ff);
    font:600 14px system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;cursor:pointer;border-radius:24px;
    box-shadow:0 6px 24px rgba(0,0,0,.45)}
  .sc-btn:hover{background:var(--bg-3,#121b22)}
  .sc-btn .sc-dot{width:8px;height:8px;border-radius:50%;background:var(--accent,#00d4ff)}
  .sc-panel{position:fixed;right:20px;bottom:20px;z-index:901;width:380px;max-width:calc(100vw - 32px);
    height:560px;max-height:calc(100vh - 40px);display:none;flex-direction:column;background:var(--bg,#080c0f);
    border:1px solid var(--border-bright,#2a4055);box-shadow:0 12px 40px rgba(0,0,0,.6);
    font:14px/1.55 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:var(--text,#d8eaf6)}
  .sc-panel.open{display:flex}
  .sc-head{display:flex;align-items:flex-start;gap:10px;padding:14px 16px;border-bottom:1px solid var(--border,#1e2d38)}
  .sc-head b{display:block;color:var(--text-bright,#e8f4ff);font-size:15px}
  .sc-head span{font-size:12px;color:var(--text-dim,#7a9fb5)}
  .sc-head .sc-x{margin-left:auto;background:none;border:none;color:var(--text-dim,#7a9fb5);font-size:18px;cursor:pointer;padding:0 2px}
  .sc-head .sc-x:hover,.sc-reset:hover{color:var(--accent,#00d4ff)}
  .sc-reset{background:none;border:none;color:var(--text-dim,#7a9fb5);font-size:12px;cursor:pointer;padding:2px 0;margin-top:2px}
  .sc-log{flex:1;overflow-y:auto;padding:14px 16px;display:flex;flex-direction:column;gap:10px}
  .sc-m{max-width:88%;padding:9px 12px;white-space:normal;word-wrap:break-word}
  .sc-m a{color:var(--accent,#00d4ff)}
  .sc-a{align-self:flex-start;background:var(--bg-2,#0d1318);border:1px solid var(--border,#1e2d38)}
  .sc-u{align-self:flex-end;background:var(--accent-dim,#006a80);color:#fff}
  .sc-e{align-self:stretch;max-width:none;font-size:13px;color:var(--text-dim,#7a9fb5);border:1px dashed var(--border-bright,#2a4055)}
  .sc-chips{display:flex;flex-wrap:wrap;gap:6px}
  .sc-chip{background:none;border:1px solid var(--border-bright,#2a4055);color:var(--text,#d8eaf6);padding:6px 10px;
    font:13px system-ui,sans-serif;cursor:pointer;border-radius:14px}
  .sc-chip:hover{border-color:var(--accent,#00d4ff);color:var(--text-bright,#e8f4ff)}
  .sc-form{display:flex;gap:8px;padding:10px 12px;border-top:1px solid var(--border,#1e2d38)}
  .sc-form textarea{flex:1;resize:none;height:42px;max-height:120px;background:var(--bg-2,#0d1318);color:var(--text-bright,#e8f4ff);
    border:1px solid var(--border-bright,#2a4055);padding:10px;font:14px system-ui,sans-serif}
  .sc-form textarea:focus{outline:none;border-color:var(--accent,#00d4ff)}
  .sc-form button{background:var(--accent,#00d4ff);color:var(--bg,#080c0f);border:none;padding:0 14px;font-weight:700;cursor:pointer}
  .sc-form button:disabled{opacity:.5;cursor:default}
  .sc-note{padding:0 12px 10px;font-size:11px;line-height:1.45;color:var(--text-dim,#7a9fb5)}
  .sc-note a{color:var(--accent,#00d4ff)}
  @media (max-width:600px){
    .sc-btn{right:14px;bottom:14px}
    .sc-panel{right:0;bottom:0;width:100vw;max-width:100vw;height:85vh;max-height:85vh}
  }`;

  async function start() {
    let on = false;
    try { on = !!(await (await fetch('/api/public/chat', { cache: 'no-store' })).json()).enabled; } catch (e) {}
    if (!on) return;

    const style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    const btn = document.createElement('button');
    btn.className = 'sc-btn';
    btn.type = 'button';
    btn.innerHTML = `<span class="sc-dot" aria-hidden="true"></span>${esc(T.open)}`;

    const panel = document.createElement('div');
    panel.className = 'sc-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', T.title);
    panel.innerHTML = `
      <div class="sc-head">
        <div><b>${esc(T.title)}</b><span>${esc(T.sub)}</span><br>
          <button class="sc-reset" type="button">${esc(T.reset)}</button></div>
        <button class="sc-x" type="button" aria-label="${esc(T.close)}">✕</button>
      </div>
      <div class="sc-log" aria-live="polite"></div>
      <form class="sc-form">
        <textarea maxlength="1000" placeholder="${esc(T.placeholder)}" aria-label="${esc(T.placeholder)}"></textarea>
        <button type="submit">${esc(T.send)}</button>
      </form>
      <div class="sc-note">${esc(T.note)} <a href="${SUPPORT}">${esc(T.human)}</a></div>`;
    document.body.appendChild(btn);
    document.body.appendChild(panel);

    const log = panel.querySelector('.sc-log');
    const form = panel.querySelector('.sc-form');
    const input = form.querySelector('textarea');
    const sendBtn = form.querySelector('button');
    let history = load();
    let busy = false;

    function bubble(cls, html) {
      const d = document.createElement('div');
      d.className = 'sc-m ' + cls;
      d.innerHTML = html;
      log.appendChild(d);
      log.scrollTop = log.scrollHeight;
      return d;
    }

    function draw() {
      log.innerHTML = '';
      bubble('sc-a', render(T.hello));
      if (!history.length) {
        const chips = document.createElement('div');
        chips.className = 'sc-chips';
        T.chips.forEach(c => {
          const b = document.createElement('button');
          b.type = 'button'; b.className = 'sc-chip'; b.textContent = c;
          b.onclick = () => ask(c);
          chips.appendChild(b);
        });
        log.appendChild(chips);
      }
      history.forEach(m => bubble(m.role === 'user' ? 'sc-u' : 'sc-a', render(m.content)));
    }

    async function ask(text) {
      text = (text || '').trim().slice(0, 1000);
      if (!text || busy) return;
      busy = true; sendBtn.disabled = true;
      history.push({ role: 'user', content: text });
      save(history);
      draw();
      const wait = bubble('sc-a', esc(T.thinking));
      try {
        const res = await fetch('/api/public/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ messages: history.slice(-MAX_SENT), lang }),
        });
        wait.remove();
        if (res.ok) {
          const d = await res.json();
          history.push({ role: 'assistant', content: d.reply });
          save(history);
          bubble('sc-a', render(d.reply));
        } else {
          // The question stays out of the history, so a retry does not send it twice.
          history.pop(); save(history);
          const m = Math.max(1, Math.ceil((parseInt(res.headers.get('Retry-After') || '60', 10) || 60) / 60));
          bubble('sc-e', esc(res.status === 429 ? T.busy.replace('{m}', m) : T.down));
        }
      } catch (e) {
        wait.remove();
        history.pop(); save(history);
        bubble('sc-e', esc(T.down));
      }
      busy = false; sendBtn.disabled = false;
      input.focus();
    }

    btn.onclick = () => { panel.classList.add('open'); btn.style.display = 'none'; draw(); input.focus(); };
    panel.querySelector('.sc-x').onclick = () => { panel.classList.remove('open'); btn.style.display = ''; };
    panel.querySelector('.sc-reset').onclick = () => { history = []; save(history); draw(); };
    form.onsubmit = e => { e.preventDefault(); const v = input.value; input.value = ''; ask(v); };
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && panel.classList.contains('open')) panel.querySelector('.sc-x').click();
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
