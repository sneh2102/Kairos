var $ = id => document.getElementById(id);
var inputs = document.querySelectorAll('[data-k]');
var SETTINGS = ['provider', 'apiKey', 'model', 'geminiKey', 'geminiModel', 'ollamaUrl', 'ollamaModel', 'ollamaKey', 'kairosUrl', 'kairosToken'];

function settings() {
  var s = {};
  for (var k of SETTINGS) s[k] = $(k).value.trim();
  return s;
}

function showProvider() {
  for (var el of document.querySelectorAll('[data-for]')) el.hidden = el.dataset.for !== $('provider').value;
}

chrome.storage.local.get(null).then(s => {
  for (var el of inputs) el.value = s.profile?.[el.dataset.k] || '';
  for (var k of SETTINGS) $(k).value = s[k] || '';
  $('provider').value = s.provider || 'claude';
  $('resumeName').textContent = s.resume?.name || 'none';
  showProvider();
});
$('provider').onchange = showProvider;

function say(msg, ok) {
  $('status').style.color = ok ? '#059669' : '#b91c1c';
  $('status').textContent = msg;
}

$('save').onclick = async () => {
  var profile = {};
  for (var el of inputs) if (el.value.trim()) profile[el.dataset.k] = el.value.trim();
  await chrome.storage.local.set({ profile, ...settings() });
  say('Saved.', true);
};

$('resume').onchange = () => {
  var file = $('resume').files[0];
  if (!file) return;
  if (file.size > 5e6) return say('That file is over 5 MB.');
  var reader = new FileReader();
  reader.onload = async () => {
    await chrome.storage.local.set({ resume: { name: file.name, type: file.type, data: reader.result } });
    $('resumeName').textContent = file.name;
    if (!/pdf/i.test(file.type)) return say('Resume file saved. For DOCX files, paste the text into the box below.', true);
    say('Resume file saved. Reading its text…', true);
    var r = await chrome.runtime.sendMessage({ type: 'extractResume', settings: settings(), pdf: reader.result.split(',')[1] }).catch(e => ({ error: e.message }));
    if (r?.error) return say('File saved, but reading the text failed: ' + r.error);
    $('resumeText').value = r.text;
    say('Resume text read. Check it, then click Save.', true);
  };
  reader.readAsDataURL(file);
};
