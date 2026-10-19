// Only `var` and function declarations at the top level: this file can be injected twice into the same page.
var aifBusy = false;

function clean(s, n) { return String(s || '').replace(/\s+/g, ' ').trim().slice(0, n || 300); }
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function shown(el) { return !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden'; }

// querySelectorAll that also looks inside open shadow roots.
function deepAll(root, sel, out) {
  out = out || [];
  out.push(...root.querySelectorAll(sel));
  for (var el of root.querySelectorAll('*')) if (el.shadowRoot) deepAll(el.shadowRoot, sel, out);
  return out;
}

function labelOf(el) {
  var root = el.getRootNode(), out = [];
  for (var id of (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean)) out.push(root.getElementById?.(id)?.innerText);
  if (el.id) out.push(root.querySelector?.('label[for="' + CSS.escape(el.id) + '"]')?.innerText);
  out.push(el.closest('label')?.innerText, el.getAttribute('aria-label'), el.getAttribute('placeholder'), el.getAttribute('title'));
  for (var d of (el.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean)) out.push(root.getElementById?.(d)?.innerText);
  return clean([...new Set(out.filter(Boolean).map(s => clean(s)))].join(' | '));
}

// Nearest ancestor text, for fields with no proper label. Skips ancestors that only repeat the field's own
// text, so a custom dropdown showing "Select Work Eligibility" picks up the question above it.
function nearby(el) {
  var own = clean(el.innerText, 400);
  for (var a = el.parentElement, i = 0; a && i < 5; a = a.parentElement, i++) {
    var t = clean(a.innerText, 400);
    if (t.length > 2 && t !== own) return t;
  }
  return '';
}

// Option elements of an open custom dropdown: role=option anywhere, or the items of the list it controls.
function optionEls(el) {
  var opts = deepAll(document, '[role=option]').filter(shown);
  var id = el && (el.getAttribute('aria-controls') || el.getAttribute('aria-owns'));
  var list = id && el.getRootNode().getElementById?.(id);
  if (!opts.length && list) opts = [...list.querySelectorAll('li,[role=option]')].filter(shown);
  return opts;
}

function groupLabel(els, opts) {
  var fs = els[0].closest('fieldset,[role=radiogroup],[role=group]');
  var l = fs && clean(fs.querySelector('legend')?.innerText || labelOf(fs));
  if (l) return l;
  var a = els[0].parentElement;
  while (a && !els.every(e => a.contains(e))) a = a.parentElement;
  // Climb until the text holds more than just the option labels, i.e. the question.
  for (var i = 0; a && i < 4; a = a.parentElement, i++) {
    var t = clean(a.innerText, 600);
    if (opts.reduce((s, o) => s.replace(o, ''), t).replace(/\W/g, '').length > 3) return t;
  }
  return els[0].name || '';
}

// Index of the option text that best matches value: exact, then prefix, then substring, then most shared words.
// Punctuation is ignored, so "Masters" matches "Master's Degree". Returns -1 if nothing matches.
function pick(texts, value) {
  var n = s => clean(s, 1000).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim(), v = n(value), t = texts.map(n);
  if (!v) return -1;
  var i = t.indexOf(v);
  if (i < 0) i = t.findIndex(x => x && (x.startsWith(v) || v.startsWith(x)));
  if (i < 0) i = t.findIndex(x => x && (x.includes(v) || v.includes(x)));
  if (i >= 0) return i;
  // ponytail: word overlap with a plural-s stem; ties go to the first option. Swap for fuzzy scoring if real forms mis-pick.
  var words = s => new Set(s.split(' ').filter(w => w.length > 2).map(w => w.replace(/s$/, '')));
  var vw = words(v), best = 0;
  t.forEach((x, j) => { var c = [...words(x)].filter(w => vw.has(w)).length; if (c > best) { best = c; i = j; } });
  return i;
}

function collect() {
  var fields = [], groups = new Map();
  // Custom dropdowns: buttons, and divs acting as a combobox or listbox trigger that don't wrap a real input.
  var SEL = 'input,textarea,select,[contenteditable=true][role=textbox],[contenteditable=true][aria-multiline],button[aria-haspopup=listbox],button[aria-haspopup=true][aria-expanded],'
    + '[role=combobox]:not(input):not(button):not(:has(input,select,button)),'
    + '[aria-haspopup=listbox]:not(input):not(button):not([role=combobox]):not(:has(input,select,button))';
  for (var el of deepAll(document, SEL)) {
    var tag = el.tagName, type = (el.getAttribute('type') || '').toLowerCase();
    if (el.disabled || el.readOnly || el.getAttribute('aria-disabled') === 'true') continue;
    if (tag === 'INPUT' && /^(hidden|submit|button|reset|image|password|search)$/.test(type)) continue;
    // Custom widgets often hide the real input behind styled markup, so a visible parent is enough for these.
    var loose = tag === 'SELECT' || /^(radio|checkbox|file)$/.test(type);
    if (!(shown(el) || loose && (shown(el.parentElement) || shown(el.labels?.[0])))) continue;

    if (type === 'radio' || type === 'checkbox') {
      var key = type + ':' + (el.name || fields.length);
      var g = groups.get(key);
      if (!g) { g = { type, els: [] }; groups.set(key, g); fields.push(g); }
      g.els.push(el);
    } else if (type === 'file') {
      if (!el.files.length) fields.push({ el, kind: 'file', label: labelOf(el) + ' ' + nearby(el) });
    } else if (tag === 'SELECT') {
      var opts = [...el.options].filter(o => !o.disabled && o.value !== '').slice(0, 300);
      var empty = !el.value || el.selectedIndex <= 0 && /select|choose|please|^[\s-]*$/i.test(el.options[0]?.text || '');
      if (empty && opts.length) fields.push({ el, kind: 'select', opts, options: opts.map(o => clean(o.text, 120)) });
    } else if (el.isContentEditable) {
      if (!clean(el.innerText)) fields.push({ el, kind: 'text', inputType: 'textarea' });
    } else if (tag !== 'INPUT' && tag !== 'TEXTAREA') {
      if (/^(select|choose|please select|-+|$)/i.test(clean(el.innerText))) fields.push({ el, kind: 'dropdown', label: clean(labelOf(el) + ' ' + nearby(el), 400) });
    } else if (el.getAttribute('role') === 'combobox' || /list|both/.test(el.getAttribute('aria-autocomplete') || '') || el.closest('[role=combobox]')) {
      // ponytail: react-select style widgets keep the chosen value outside the input; checks the value container, extend if a site's widget gets refilled
      var box = el.closest('[class*="value-container"],[class*="ValueContainer"]') || el.parentElement?.parentElement;
      var shownText = clean(box?.innerText);
      if (!el.value && (!shownText || /^(select|choose|start typing|search|type)/i.test(shownText))) fields.push({ el, kind: 'combobox' });
    } else if (!el.value) {
      fields.push({ el, kind: 'text', inputType: tag === 'TEXTAREA' ? 'textarea' : type || 'text' });
    }
  }
  return fields.flatMap(f => {
    if (!f.els) {
      f.label = f.label || labelOf(f.el);
      if (f.label.length < 3) f.label = clean(f.label + ' ' + nearby(f.el));
      return [f];
    }
    if (f.els.some(e => e.checked)) return [];
    if (f.type === 'checkbox' && f.els.length === 1) return [{ el: f.els[0], kind: 'checkbox', label: labelOf(f.els[0]) || nearby(f.els[0]) }];
    var options = f.els.map(e => labelOf(e) || e.value);
    return [{ el: f.els[0], els: f.els, kind: f.type === 'radio' ? 'radio' : 'checkboxes', options, label: groupLabel(f.els, options) }];
  });
}

// Use the native setter so React, Vue and Angular see the change.
function setValue(el, v) {
  var proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}

function press(el) {
  for (var t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
    el.dispatchEvent(new (t.startsWith('pointer') ? PointerEvent : MouseEvent)(t, { bubbles: true, cancelable: true, view: window }));
  }
}

// Workday-style dropdowns only render their options when open: open, read the options, close.
async function peek(el) {
  el.click();
  var opts = [];
  for (var t = 0; t < 10 && !opts.length; t++) {
    await sleep(60);
    opts = optionEls(el).map(o => clean(o.innerText, 120));
  }
  el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  await sleep(50);
  if (optionEls(el).length) el.click();
  return opts.length ? opts.slice(0, 300) : undefined;
}

// Closes a custom dropdown that is still showing its options: Escape first, then toggle the trigger, then blur.
async function closeList(el) {
  for (var step = 0; step < 3 && optionEls(el).length; step++) {
    if (step === 0) el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', keyCode: 27, bubbles: true }));
    else if (step === 1) el.click();
    else (document.activeElement || el).blur?.();
    await sleep(120);
  }
}

// Wait for a custom dropdown's options to render, click the best match and make sure the list closes.
// If nothing matches (or the options never show up), the list is closed again instead of being left open.
async function choose(v, el) {
  for (var t = 0; t < 20; t++) {
    await sleep(100);
    var opts = optionEls(el);
    var i = pick(opts.map(o => clean(o.innerText, 200)), v);
    if (i >= 0) {
      press(opts[i]);
      await sleep(150);
      if (optionEls(el).length) { opts[i].click(); await sleep(150); } // some widgets only react to a plain click
      await closeList(el);
      return true;
    }
  }
  await closeList(el);
  return false;
}

// Clicks a radio or checkbox even when the real input is hidden behind styled markup.
function toggle(e) {
  (shown(e) ? e : e.labels?.[0] || e.parentElement).click();
}

async function apply(f, v) {
  var el = f.el, i;
  switch (f.kind) {
    case 'text':
      if (el.isContentEditable) { // rich text editors (cover letter boxes)
        el.focus(); document.execCommand('selectAll'); document.execCommand('insertText', false, v); el.blur();
        return !!clean(el.innerText);
      }
      if (f.inputType === 'number') v = v.replace(/[^\d.\-]/g, '');
      if (el.maxLength > 0) v = v.slice(0, el.maxLength);
      if (!v) return false;
      el.focus(); setValue(el, v); el.blur();
      return el.value === v; // false when the framework reset it
    case 'select':
      if ((i = pick(f.options, v)) < 0) return false;
      setValue(el, f.opts[i].value);
      return true;
    case 'checkbox':
      if (/^(true|yes)$/i.test(v) !== el.checked) toggle(el);
      return true;
    case 'checkboxes':
      // Some models return "A, B, C" as one answer instead of one entry per option.
      var exact = f.options.some(o => o.toLowerCase() === clean(v).toLowerCase());
      var hit = false;
      for (var part of exact ? [v] : v.split(/\s*[,;\n]\s*/)) {
        if ((i = pick(f.options, part)) < 0) continue;
        if (!f.els[i].checked) toggle(f.els[i]);
        f.el = f.els[i];
        hit = true;
      }
      return hit;
    case 'radio':
      if ((i = pick(f.options, v)) < 0) return false;
      if (!f.els[i].checked) toggle(f.els[i]);
      f.el = f.els[i];
      return true;
    case 'combobox':
      el.focus(); setValue(el, v);
      await choose(v, el); // no match: leave the typed text (free-text comboboxes keep it), list is closed
      el.blur();
      return true;
    case 'dropdown':
      el.click();
      if (!await choose(v, el)) return false;
      // Still showing the placeholder means the click didn't register.
      return !/^(select|choose|please select|-+|$)/i.test(clean(el.innerText));
  }
  return false;
}

function attach(el, r) {
  var bin = atob(r.data.split(',')[1]);
  var dt = new DataTransfer();
  dt.items.add(new File([Uint8Array.from(bin, c => c.charCodeAt(0))], r.name, { type: r.type }));
  el.files = dt.files;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}

function mark(f) {
  var t = shown(f.el) ? f.el : f.el.labels?.[0] || f.el.parentElement;
  if (t) { t.style.outline = '2px solid #8b5cf6'; t.style.outlineOffset = '2px'; }
}

function toast(msg, isError) {
  var t = document.getElementById('aif-toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'aif-toast';
    t.setAttribute('role', 'status');
    t.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483647;max-width:360px;padding:10px 14px;border-radius:8px;font:13px/1.4 system-ui,sans-serif;color:#fff;box-shadow:0 4px 16px rgba(0,0,0,.25)';
    document.documentElement.appendChild(t);
  }
  t.style.background = isError ? '#b91c1c' : '#4c1d95';
  t.textContent = msg;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.remove(), isError ? 10000 : 6000);
}

async function fill() {
  if (aifBusy) return;
  aifBusy = true;
  try {
    var fields = collect(), n = 0, failed = 0;
    if (!fields.length) return; // nothing to do in this frame (ads, widgets, an already-filled form)
    var { resume } = await chrome.storage.local.get('resume');
    for (var f of fields) {
      if (f.kind === 'file' && resume && /resume|cv\b|curriculum/i.test(f.label) && !/cover/i.test(f.label)) { attach(f.el, resume); n++; }
    }
    var asked = fields.filter(f => f.kind !== 'file');
    for (var d of asked) if (d.kind === 'dropdown') d.options = await peek(d.el);
    if (asked.length) {
      toast(`AI Autofill: reading ${asked.length} field(s)…`);
      var page = clean(document.title + '\n' + (document.body?.innerText || ''), 8000);
      var payload = asked.map((f, id) => ({ id: String(id), kind: f.kind, label: f.label, options: f.options, inputType: f.inputType, maxLength: f.el.maxLength > 0 ? f.el.maxLength : undefined, required: f.el.required || f.el.getAttribute('aria-required') === 'true' || undefined }));
      var r = await chrome.runtime.sendMessage({ type: 'ask', fields: payload, page });
      if (!r || r.error) throw new Error(r?.error || 'No reply from the extension. Try again.');
      for (var a of r.answers) {
        var g = asked[+a.id];
        if (g && g.el.isConnected && await apply(g, a.value)) { mark(g); n++; } else if (g) failed++;
      }
      failed += asked.length - r.answers.length; // fields the model left out
    }
    toast(`AI Autofill: filled ${n} field(s)${failed ? `, ${failed} left for you` : ''}. Check them before you submit.`);
  } catch (e) {
    toast('AI Autofill: ' + e.message, true);
  } finally {
    aifBusy = false;
  }
}

if (typeof chrome !== 'undefined' && chrome.runtime?.onMessage && !window.__aifLoaded) {
  window.__aifLoaded = true;
  chrome.runtime.onMessage.addListener((m, _s, reply) => {
    if (m.type !== 'fill') return;
    reply({ ok: true });
    fill();
  });
}
