#!/usr/bin/env node
// 文字答案填入 -> 暂时保存(绝不提交)
// 用法: node fill-save.js <课程名> <作业名> <答案JSON路径> [--tag=x]
// 答案JSON: {"1":"第1题文本","2":"..."} 键为题号(1-based)
const { chromium } = require('../lib/playwright');
const path = require('path'); const fs = require('fs');
const { COOKIES: COOKFILE, PROFILE, OUT: OUTDIR } = require('../lib/config');
const KEY = process.argv[2], WORK = process.argv[3], ANSFILE = process.argv[4];
const TAG = ((process.argv.find(a => a.startsWith('--tag=')) || '=hw').split('=')[1]).replace(/[^\w.-]/g, '_');
if (!KEY || !WORK || !ANSFILE) { console.error('用法: fill-save.js <课程> <作业> <答案.json>'); process.exit(64); }
const ANS = JSON.parse(fs.readFileSync(ANSFILE, 'utf8'));
const log = (...a) => console.log('[fill-save]', ...a);

async function openWork(ctx) {
  const page = ctx.pages()[0] || await ctx.newPage();
  await page.goto('https://mooc1.chaoxing.com/mycourse/studentcourse', { timeout: 45000, waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4500);
  const s = (page.url().match(/[?&]s=([a-f0-9]+)/) || [])[1];
  if (!s) { log('NEED_RELOGIN', page.url().slice(0, 90)); return { err: 'NEED_RELOGIN' }; }
  await page.goto('http://mooc1-1.chaoxing.com/visit/interaction?s=' + s, { timeout: 45000, waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4500);
  const target = await page.evaluate((k) => {
    const list = [...document.querySelectorAll('a[href*="stucoursemiddle"]')].map(a => ({ name: (a.innerText || '').trim().replace(/\s+/g, ' '), href: a.href }));
    return list.find(x => x.name.replace(/[《》]/g, '') === k) || list.find(x => x.name.replace(/[《》]/g, '').includes(k)) || null;
  }, KEY);
  if (!target) { log('NO_COURSE', KEY); return { err: 'NO_COURSE' }; }
  await page.goto(target.href, { timeout: 45000, waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(5000);
  await page.evaluate(() => { for (const el of [...document.querySelectorAll('a, li, div, span, p')]) { if ((el.innerText || '').trim() === '作业' && el.offsetParent !== null) { el.click(); return; } } });
  let wf = null;
  for (let i = 0; i < 12; i++) { await page.waitForTimeout(1500); wf = page.frames().find(f => f.url().includes('/work/')); if (wf) break; }
  if (!wf) { log('NO_WORK_FRAME'); return { err: 'NO_WORK_FRAME' }; }
  await wf.waitForTimeout(2000);
  const clicked = await wf.evaluate((w) => {
    const el = [...document.querySelectorAll('div, li, a, span, p, td')].find(e => (e.innerText || '').trim() === w) || [...document.querySelectorAll('div, li, a, span, p, td')].find(e => (e.innerText || '').trim().startsWith(w) && (e.innerText || '').length < w.length + 12);
    if (!el) return 'NOT_FOUND';
    let ct = el; for (let i = 0; i < 6 && ct; i++, ct = ct.parentElement) { if (ct.getAttribute('onclick') || ct.tagName === 'A') break; } ct.click(); return 'OK';
  }, WORK);
  if (clicked !== 'OK') { log('点击作业失败', clicked); return { err: 'CLICK_' + clicked }; }
  await page.waitForTimeout(9000);
  const wp = ctx.pages().find(p => p.url().includes('dowork')) || page;
  await wp.waitForTimeout(4000);
  await wp.evaluate(() => { [...document.querySelectorAll('button, a, div, span')].forEach(el => { if ((el.innerText || '').trim() === '知道了' && el.offsetParent !== null) { try { el.click(); } catch (e) {} } }); });
  await wp.waitForTimeout(1200);
  log('答题页:', wp.url().slice(0, 130));
  return { wp };
}

async function tempSave(wp) {
  const saved = await wp.evaluate(() => {
    const t = [...document.querySelectorAll('a, button, div, span')].find(e => (e.innerText || '').trim() === '暂时保存' && e.offsetParent !== null && !e.closest('[class*="dialog"], [class*="mask"], .pop'));
    if (t) { t.click(); return 'OK'; } return 'NO_BUTTON';
  });
  log('暂时保存:', saved);
  await wp.waitForTimeout(4000);
  return saved;
}

(async () => {
  fs.mkdirSync(OUTDIR, { recursive: true });
  const cookies = JSON.parse(fs.readFileSync(COOKFILE, 'utf8'));
  const ctx = await chromium.launchPersistentContext(PROFILE, { channel: 'msedge', headless: true, viewport: { width: 1360, height: 900 } });
  await ctx.addCookies(cookies);
  try {
    const r = await openWork(ctx);
    if (r.err) process.exit(r.err === 'NEED_RELOGIN' ? 2 : 3);
    const wp = r.wp;
    for (const [n, text] of Object.entries(ANS)) {
      const i = Number(n) - 1;
      const fh = await wp.$('#ueditor_' + i);
      if (!fh) { log('缺编辑器 Q' + n); continue; }
      const fr = await fh.contentFrame();
      if (!fr) { log('无frame Q' + n); continue; }
      await fr.locator('body').click({ timeout: 5000 }).catch(() => {});
      await wp.waitForTimeout(200);
      await wp.keyboard.press('Meta+A').catch(() => {});
      await wp.keyboard.press('Backspace').catch(() => {});
      await wp.waitForTimeout(200);
      await wp.keyboard.type(String(text), { delay: 8 });
      await wp.waitForTimeout(500);
      await wp.evaluate(({ i, text }) => {
        const ta = [...document.querySelectorAll('textarea')][i];
        if (ta) { const st = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set; st.call(ta, text); ta.dispatchEvent(new Event('input', { bubbles: true })); }
      }, { i, text });
      const got = await fr.evaluate(() => document.body.innerText).catch(() => 'ERR');
      log('Q' + n + ' 填入', String(text).length, '字 回读', got.length, '字');
      await wp.waitForTimeout(400);
    }
    await wp.screenshot({ path: path.join(OUTDIR, 'fill-' + TAG + '.png'), fullPage: true });
    await tempSave(wp);
    log('完成 — 未提交');
  } finally { await ctx.close(); }
})().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
