/* biasprobe front-end: story highlighting, span marking, annotation/review/predict flows. */
(function () {
  const BP = window.BP = {};

  const LABEL_COLORS = {
    gender_role: '#d94a8c', gender_trait: '#b03aa5', racial_ethnic: '#c0392b', xenophobia: '#e67e22',
    religion: '#8e6b2b', age: '#2e8b57', disability: '#1f8aa8', class: '#6c5ce7', sexuality: '#0984e3',
    appearance: '#a0892c', other: '#636e72', regional: '#3b7d3b', profession: '#7a5230',
    family_structure: '#c2185b', mental_health: '#00897b', political: '#5d4037', savior: '#d35400',
  };
  const color = (l) => LABEL_COLORS[l] || LABEL_COLORS.other;
  const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* ---------------------------------------------------------- highlighting */
  // spans: [{start, end, label, kind: 'ev'|'lex'|'user', title}]
  BP.renderStory = function (el, text, spans) {
    const cuts = new Set([0, text.length]);
    spans.forEach((s) => { cuts.add(Math.max(0, Math.min(text.length, s.start))); cuts.add(Math.max(0, Math.min(text.length, s.end))); });
    const points = Array.from(cuts).sort((a, b) => a - b);
    let html = '';
    for (let i = 0; i < points.length - 1; i++) {
      const a = points[i], b = points[i + 1];
      if (a === b) continue;
      const seg = text.slice(a, b);
      const covering = spans.filter((s) => s.start <= a && s.end >= b);
      if (!covering.length) { html += esc(seg); continue; }
      const kinds = Array.from(new Set(covering.map((s) => s.kind))).join(' ');
      const first = covering.find((s) => s.kind === 'user') || covering[0];
      const title = covering.map((s) => `${s.label}${s.title ? ': ' + s.title : ''}`).join('\n');
      html += `<mark class="${kinds}" style="--c:${color(first.label)}" title="${esc(title)}">${esc(seg)}</mark>`;
    }
    el.innerHTML = html;
  };

  function modelSpans(prediction, onlyPredicted) {
    const out = [];
    if (!prediction || !prediction.evidence || !prediction.evidence.labels) return out;
    for (const [label, info] of Object.entries(prediction.evidence.labels)) {
      if (onlyPredicted && !info.predicted) continue;
      (info.evidence || []).forEach((e) => out.push({ start: e.start, end: e.end, label, kind: 'ev', title: (e.cues || []).join(', ') }));
    }
    return out;
  }
  function lexSpans(lexical) {
    return (lexical || []).map((e) => ({ start: e.start, end: e.end, label: e.label, kind: 'lex', title: (e.cues || []).join(', ') }));
  }

  function selectionOffsets(container) {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
    const range = sel.getRangeAt(0);
    if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) return null;
    const pre = document.createRange();
    pre.selectNodeContents(container);
    pre.setEnd(range.startContainer, range.startOffset);
    const start = pre.toString().length;
    const end = start + range.toString().length;
    return end > start ? { start, end } : null;
  }

  /* ------------------------------------------------------------- helpers */
  async function postJSON(url, body, method = 'POST') {
    const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || data.reason || r.statusText);
    return data;
  }
  const store = {
    get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch (e) { return d; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } },
  };

  /* --------------------------------------------------------- train button */
  BP.wireTrainButton = function (btn, msg, log) {
    if (!btn) return;
    let timer = null;
    const poll = async () => {
      const st = await fetch('/api/train/status').then((r) => r.json());
      if (log) { log.classList.remove('hidden'); log.textContent = (st.log || []).join('\n'); log.scrollTop = log.scrollHeight; }
      if (st.running) { msg.textContent = 'training…'; timer = setTimeout(poll, 1500); return; }
      btn.disabled = false;
      msg.textContent = st.error ? 'failed: ' + st.error : (st.last ? `done: ${st.last.version}, ${st.last.predicted} predictions refreshed. Reloading…` : '');
      if (!st.error) setTimeout(() => location.reload(), 1200);
    };
    btn.addEventListener('click', async () => {
      btn.disabled = true; msg.textContent = 'starting…';
      try { await postJSON('/api/train', {}); poll(); }
      catch (e) { btn.disabled = false; msg.textContent = e.message; }
    });
  };

  /* --------------------------------------------------------- story view */
  BP.initStoryView = function () {
    const data = JSON.parse(document.getElementById('story-data').textContent);
    const storyEl = document.getElementById('story');
    const userSpans = (data.existing_spans || []).map((s) => ({ ...s, kind: 'user' }));
    const draw = () => {
      let spans = [];
      if (document.getElementById('show-model-ev')?.checked) spans = spans.concat(modelSpans(data.prediction, true));
      if (document.getElementById('show-lex-ev')?.checked) spans = spans.concat(lexSpans(data.lexical));
      if (document.getElementById('show-user-spans')?.checked) spans = spans.concat(userSpans);
      BP.renderStory(storyEl, data.text, spans);
    };
    ['show-model-ev', 'show-lex-ev', 'show-user-spans'].forEach((id) => document.getElementById(id)?.addEventListener('change', draw));
    draw();
  };

  /* --------------------------------------------------------- annotate page */
  BP.initAnnotate = function () {
    const root = document.getElementById('annotate-root');
    const data = JSON.parse(document.getElementById('story-data').textContent);
    const storyEl = document.getElementById('story');
    const menu = document.getElementById('span-menu');
    const form = document.getElementById('label-form');
    const spanList = document.getElementById('span-list');
    const saveMsg = document.getElementById('save-msg');
    const annotator = document.getElementById('annotator');
    const storyId = parseInt(root.dataset.storyId, 10);
    const mode = root.dataset.mode;
    const userSpans = (data.existing_spans || []).map((s) => ({ ...s, kind: 'user' }));
    annotator.value = store.get('bp.annotator', '');

    const checkboxes = () => Array.from(form.querySelectorAll('input[name=labels]'));
    const checked = () => checkboxes().filter((c) => c.checked).map((c) => c.value);

    const draw = () => {
      let spans = [];
      if (document.getElementById('show-model-ev').checked) spans = spans.concat(modelSpans(data.prediction, true));
      if (document.getElementById('show-lex-ev').checked) spans = spans.concat(lexSpans(data.lexical));
      if (document.getElementById('show-user-spans').checked) spans = spans.concat(userSpans);
      BP.renderStory(storyEl, data.text, spans);
      spanList.innerHTML = userSpans.length ? '' : '<li class="muted">none</li>';
      userSpans.forEach((s, i) => {
        const li = document.createElement('li');
        li.innerHTML = `<span class="tag lab-${s.label}">${s.label}</span><span class="q">“${esc(data.text.slice(s.start, s.end))}”</span><button type="button" title="remove">✕</button>`;
        li.querySelector('button').addEventListener('click', () => { userSpans.splice(i, 1); draw(); });
        spanList.appendChild(li);
      });
      checkboxes().forEach((c) => c.closest('.label-item').classList.toggle('on', c.checked));
    };
    ['show-model-ev', 'show-lex-ev', 'show-user-spans'].forEach((id) => document.getElementById(id).addEventListener('change', draw));
    form.addEventListener('change', (e) => { if (e.target.name === 'labels') draw(); });

    // text selection -> label menu -> span
    storyEl.addEventListener('mouseup', () => {
      setTimeout(() => {
        const off = selectionOffsets(storyEl);
        if (!off) { menu.classList.add('hidden'); return; }
        menu.innerHTML = '';
        data.labels.forEach((lab) => {
          const b = document.createElement('button');
          b.type = 'button'; b.textContent = lab.name; b.style.background = color(lab.key);
          b.addEventListener('click', () => {
            userSpans.push({ start: off.start, end: off.end, label: lab.key, kind: 'user' });
            const cb = form.querySelector(`input[name=labels][value="${lab.key}"]`);
            if (cb) cb.checked = true;
            window.getSelection().removeAllRanges();
            menu.classList.add('hidden');
            draw();
          });
          menu.appendChild(b);
        });
        const rect = window.getSelection().getRangeAt(0).getBoundingClientRect();
        const prect = storyEl.closest('.story-pane').getBoundingClientRect();
        menu.style.left = Math.max(0, rect.left - prect.left) + 'px';
        menu.style.top = (rect.bottom - prect.top + 6) + 'px';
        menu.classList.remove('hidden');
      }, 0);
    });
    document.addEventListener('mousedown', (e) => { if (!menu.contains(e.target) && !storyEl.contains(e.target)) menu.classList.add('hidden'); });

    // keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) && !(e.ctrlKey && e.key === 'Enter')) return;
      if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); form.requestSubmit(); return; }
      if (/^[0-9]$/.test(e.key)) {
        const idx = e.key === '0' ? 9 : parseInt(e.key, 10) - 1;
        const cb = checkboxes()[idx];
        if (cb) { cb.checked = !cb.checked; draw(); }
      } else if (e.key === 'n') { checkboxes().forEach((c) => (c.checked = false)); draw(); }
    });
    document.getElementById('nobias-btn').addEventListener('click', () => { checkboxes().forEach((c) => (c.checked = false)); draw(); form.requestSubmit(); });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      store.set('bp.annotator', annotator.value);
      const labels = checked();
      const decisions = {};
      checkboxes().forEach((c) => {
        const predicted = c.dataset.predicted === '1';
        if (predicted && c.checked) decisions[c.value] = 'accepted';
        else if (predicted && !c.checked) decisions[c.value] = 'rejected';
        else if (!predicted && c.checked) decisions[c.value] = 'added';
      });
      const strategy = document.getElementById('strategy').value;
      saveMsg.textContent = 'saving…';
      try {
        const res = await postJSON('/api/annotations', {
          story_id: storyId, labels, spans: userSpans.map(({ start, end, label }) => ({ start, end, label })),
          notes: document.getElementById('notes').value, annotator: annotator.value,
          kind: mode === 'review' ? 'review' : 'manual', decisions, next_strategy: strategy,
          model_filter: root.dataset.modelFilter || null,
        });
        saveMsg.textContent = `saved (${res.stats.annotated} annotated so far)`;
        const q = `?strategy=${strategy}&mode=${mode}` + (root.dataset.modelFilter ? `&model=${encodeURIComponent(root.dataset.modelFilter)}` : '');
        location.href = res.next_story_id ? `/annotate/${res.next_story_id}${q}` : `/stories?annotated=0&done=1`;
      } catch (err) { saveMsg.textContent = 'error: ' + err.message; }
    });
    draw();
  };

  /* ----------------------------------------------------------- predict page */
  BP.initPredict = function () {
    const labels = JSON.parse(document.getElementById('labels-data').textContent);
    const input = document.getElementById('story-input');
    const storyEl = document.getElementById('story');
    const form = document.getElementById('label-form');
    const list = document.getElementById('result-list');
    const msg = document.getElementById('predict-msg');
    const saveMsg = document.getElementById('save-msg');
    const annotator = document.getElementById('annotator');
    annotator.value = store.get('bp.annotator', '');
    let last = null;

    const draw = () => {
      if (!last) return;
      let spans = [];
      if (document.getElementById('show-model-ev').checked && last.labels) {
        spans = spans.concat(modelSpans({ evidence: { labels: last.labels } }, true));
      }
      if (document.getElementById('show-lex-ev').checked) spans = spans.concat(lexSpans(last.lexical_evidence));
      BP.renderStory(storyEl, last.text, spans);
    };
    ['show-model-ev', 'show-lex-ev'].forEach((id) => document.getElementById(id).addEventListener('change', draw));

    document.getElementById('predict-btn').addEventListener('click', async () => {
      const text = input.value.trim();
      if (!text) { msg.textContent = 'Paste a story first.'; return; }
      msg.textContent = 'analysing…';
      try {
        const res = await postJSON('/api/predict', { text });
        last = { ...res, text };
        storyEl.classList.remove('hidden'); document.getElementById('toggles').classList.remove('hidden');
        list.innerHTML = '';
        labels.forEach((lab) => {
          const info = res.labels ? res.labels[lab.key] : null;
          const li = document.createElement('li');
          li.className = `label-item lab-${lab.key}` + (info && info.predicted ? ' on' : '');
          const score = info ? `<span class="score"><span class="bar"><span style="width:${Math.round(info.score * 100)}%"></span></span>${info.score.toFixed(2)}${info.trained ? '' : '<span class="muted" title="too few examples">?</span>'}</span>` : '';
          const ev = info && info.evidence.length ? `<ul class="ev-list">${info.evidence.slice(0, 3).map((e) => `<li>“${esc(e.sentence)}” <span class="muted">(${(e.cues || []).join(', ')})</span></li>`).join('')}</ul>` : '';
          const feats = info && info.top_features.length ? `<div class="feats">cues: ${info.top_features.slice(0, 4).map((f) => `<code>${esc(f.feature)}</code>`).join(' ')}</div>` : '';
          li.innerHTML = `<label class="label-head"><input type="checkbox" name="labels" value="${lab.key}" ${info && info.predicted ? 'checked' : ''} data-predicted="${info && info.predicted ? 1 : 0}"><span class="name">${esc(lab.name)}</span>${score}</label><div class="label-desc">${esc(lab.description)}${feats}${ev}</div>`;
          list.appendChild(li);
        });
        form.classList.remove('hidden');
        const flagged = res.flagged || [];
        msg.textContent = res.labels
          ? (flagged.length ? `Model ${res.model_version} perceives: ${flagged.join(', ')}. Correct it below if needed.` : `Model ${res.model_version} perceives no stereotype. Add labels below if you disagree.`)
          : res.message;
        draw();
      } catch (err) { msg.textContent = 'error: ' + err.message; }
    });
    form.addEventListener('change', (e) => { if (e.target.name === 'labels') e.target.closest('.label-item').classList.toggle('on', e.target.checked); });
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!last) return;
      store.set('bp.annotator', annotator.value);
      const chosen = Array.from(form.querySelectorAll('input[name=labels]:checked')).map((c) => c.value);
      saveMsg.textContent = 'saving…';
      try {
        const res = await postJSON('/api/stories', { text: last.text, model: document.getElementById('story-model').value || 'manual', labels: chosen, notes: document.getElementById('notes').value, annotator: annotator.value });
        saveMsg.innerHTML = `saved as <a href="/story/${res.story_id}">story ${res.story_id}</a>. Retrain from the dashboard to use it.`;
      } catch (err) { saveMsg.textContent = 'error: ' + err.message; }
    });
  };
})();
