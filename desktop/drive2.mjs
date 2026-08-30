import { _electron as electron } from 'playwright-core';

async function main() {
  const app = await electron.launch({
    executablePath: 'D:\\GitHub\\Kairos\\desktop\\node_modules\\electron\\dist\\electron.exe',
    args: ['D:\\GitHub\\Kairos\\desktop'],
    timeout: 30000,
  });

  app.process().stdout.on('data', (d) => process.stdout.write(`[main] ${d}`));
  app.process().stderr.on('data', (d) => process.stderr.write(`[main-err] ${d}`));

  const page = await app.firstWindow();
  await page.waitForLoadState('domcontentloaded');
  console.log('URL:', page.url());

  await new Promise(r => setTimeout(r, 2000));
  const clickSettings = await page.evaluate(() => {
    const el = [...document.querySelectorAll('a')].find(a => a.textContent?.trim() === 'Settings');
    if (!el) return 'NOT_FOUND: ' + [...document.querySelectorAll('a')].map(a=>a.textContent?.trim()).join('|');
    el.click();
    return 'OK';
  });
  console.log('click settings ->', clickSettings);
  await new Promise(r => setTimeout(r, 2000));

  const clickDesktop = await page.evaluate(() => {
    const el = [...document.querySelectorAll('button')].find(b => b.textContent?.trim().toLowerCase() === 'desktop');
    if (!el) return 'NOT_FOUND: ' + [...document.querySelectorAll('button')].map(b=>b.textContent?.trim()).join('|');
    el.click();
    return 'OK';
  });
  console.log('click desktop tab ->', clickDesktop);
  await new Promise(r => setTimeout(r, 1000));

  const initial = await page.evaluate(() => [...document.querySelectorAll('input[type=checkbox]')].map(c => c.checked));
  console.log('initial checkbox state:', initial);

  // check both ON (only click if currently unchecked, so re-runs are idempotent)
  await page.evaluate(() => {
    document.querySelectorAll('input[type=checkbox]').forEach(c => { if (!c.checked) c.click(); });
  });
  await new Promise(r => setTimeout(r, 300));

  await page.evaluate(() => {
    const el = [...document.querySelectorAll('button')].find(b => b.textContent?.includes('Save changes'));
    el?.click();
  });
  await new Promise(r => setTimeout(r, 1500));

  const savedText = await page.evaluate(() => document.body.innerText.includes('Saved'));
  console.log('save confirmed in UI:', savedText);

  // Inspect main-process state: tray exists? what does getDesktopConfig() see right now?
  const mainState = await app.evaluate(({ app: electronApp }, arg) => {
    // eslint-disable-next-line no-undef
    return { note: 'see stdout of electron process for details' };
  });

  console.log('--- closing window (simulates clicking X) ---');
  await page.close();
  await new Promise(r => setTimeout(r, 1500));

  const windowsAfterClose = app.windows().length;
  console.log('windows still open after close:', windowsAfterClose);

  await app.close().catch(() => {});
  console.log('DONE');
}

main().catch(e => { console.error('ERROR', e); process.exit(1); });
