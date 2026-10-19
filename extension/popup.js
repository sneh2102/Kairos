document.getElementById('fill').onclick = async () => {
  var status = document.getElementById('status');
  status.textContent = 'Starting…';
  var r = await chrome.runtime.sendMessage({ type: 'fillActive' }).catch(e => ({ error: e.message }));
  status.textContent = r?.error ? "Can't run on this page: " + r.error : 'Working. Watch the page for progress.';
};
