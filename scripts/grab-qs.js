#!/usr/bin/env node
// 抓取作业题目:每题截高清图 + 导出 HTML(公式 LaTeX 在 data 属性里)
const { chromium } = require('../lib/playwright');
const path = require('path'); const fs = require('fs');
const { COOKIES: COOKFILE, PROFILE, OUT: OUTROOT } = require('../lib/config');
const OUT = process.argv[4] || path.join(OUTROOT, 'grab');
const KEY = process.argv[2], WORK = process.argv[3];
const log = (...a) => console.log('[grab]', ...a);

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const cookies = JSON.parse(fs.readFileSync(COOKFILE, 'utf8'));
  const ctx = await chromium.launchPersistentContext(PROFILE, { channel: 'msedge', headless: true, viewport: { width: 1400, height: 1000 }, deviceScaleFactor: 2 });
  await ctx.addCookies(cookies);
  try {
    const page = ctx.pages()[0] || await ctx.newPage();
    await page.goto('https://mooc1.chaoxing.com/mycourse/studentcourse', { timeout: 45000, waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(4500);
    const s = (page.url().match(/[?&]s=([a-f0-9]+)/) || [])[1];
    if (!s) { log('NEED_RELOGIN'); process.exit(2); }
    await page.goto('http://mooc1-1.chaoxing.com/visit/interaction?s=' + s, { timeout: 45000, waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(4500);
    const norm = t => (t || '').replace(/[《》]/g, '');
    const target = await page.evaluate(({ k }) => {
      const list = [...document.querySelectorAll('a[href*="stucoursemiddle"]')].map(a => ({ name: (a.innerText || '').trim().replace(/\s+/g, ' '), href: a.href }));
      return list.find(x => x.name.replace(/[《》]/g, '') === k) || null;
    }, { k: norm(KEY) });
    if (!target) { log('NO_COURSE'); process.exit(3); }
    await page.goto(target.href, { timeout: 45000, waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(5000);
    await page.evaluate(() => { for (const el of [...document.querySelectorAll('a, li, div, span, p')]) { if ((el.innerText || '').trim() === '作业' && el.offsetParent !== null) { el.click(); return; } } });
    let wf = null;
    for (let i = 0; i < 12; i++) { await page.waitForTimeout(1500); wf = page.frames().find(f => f.url().includes('/work/')); if (wf) break; }
    if (!wf) { log('NO_WORK_FRAME'); process.exit(4); }
    await wf.waitForTimeout(2000);
    await wf.evaluate((workName) => {
      const el = [...document.querySelectorAll('div, li, a, span, p, td')].find(e => (e.innerText || '').trim() === workName);
      let ct = el; for (let i = 0; i < 6 && ct; i++, ct = ct.parentElement) { if (ct.getAttribute('onclick') || ct.tagName === 'A') break; } ct.click();
    }, WORK);
    await page.waitForTimeout(9000);
    const wp = ctx.pages().find(p => p.url().includes('dowork')) || page;
    await wp.waitForTimeout(4000);
    await wp.evaluate(() => { [...document.querySelectorAll('button, a, div, span')].forEach(el => { if ((el.innerText || '').trim() === '知道了' && el.offsetParent !== null) { try { el.click(); } catch (e) {} } }); });
    await wp.waitForTimeout(1500);

    const meta = await wp.evaluate(() => ({ url: location.href, text: document.body.innerText }));
    fs.writeFileSync(path.join(OUT, 'page-text.txt'), meta.text);
    log('页面文本前 200:', meta.text.replace(/\n+/g, ' | ').slice(0, 200));

    const infos = await wp.evaluate(() => {
      return [...document.querySelectorAll('[id^="question"]')].filter(e => /^question\d+$/.test(e.id)).map((q, i) => {
        const qid = q.id.replace('question', '');
        const stem = q.querySelector('.Zy_TItle, .questionTit, .mark_name, .qtContent') || q;
        const html = (stem.innerHTML || '');
        const latex = [...q.querySelectorAll('img[data]')].map(img => ({ src: (img.getAttribute('src')||'').slice(0,120), data: img.getAttribute('data') }));
        return { i: i + 1, qid, typename: q.getAttribute('typename'), text: (stem.innerText || '').trim().slice(0, 500), htmlLen: html.length, latex };
      });
    });
    fs.writeFileSync(path.join(OUT, 'questions.json'), JSON.stringify(infos, null, 1));
    log('题目数:', infos.length);
    for (const q of infos) {
      log('Q' + q.i, q.typename, '| latex imgs:', q.latex.length, '|', q.text.replace(/\n+/g, ' ').slice(0, 80));
      const el = await wp.$('#question' + q.qid);
      if (el) await el.screenshot({ path: path.join(OUT, 'q' + q.i + '.png') }).catch(e => log('  shot err', e.message.slice(0, 50)));
    }
    await wp.screenshot({ path: path.join(OUT, 'page-full.png'), fullPage: true });
    log('输出目录:', OUT);
  } finally { await ctx.close(); }
})().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
