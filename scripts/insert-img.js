#!/usr/bin/env node
// 手写答题纸图片 -> 上传到学习通UEditor -> 插入第N题编辑器 -> 暂时保存(不提交)
// 用法: node insert-img.js <课程> <作业名> <题号1-based> <图片路径>
const { chromium } = require('../lib/playwright');
const path = require('path'); const fs = require('fs');
const fsB64 = p => fs.readFileSync(p).toString('base64');
const { COOKIES: COOKFILE, PROFILE, OUT: OUTDIR } = require('../lib/config');
const KEY = process.argv[2], WORK = process.argv[3], QN = Number(process.argv[4]), IMG = process.argv[5];
fs.mkdirSync(OUTDIR, { recursive: true });
const log = (...a) => console.log('[imgsave]', ...a);

(async () => {
  const cookies = JSON.parse(fs.readFileSync(COOKFILE, 'utf8'));
  const ctx = await chromium.launchPersistentContext(PROFILE, { channel: 'msedge', headless: true, viewport: { width: 1360, height: 900 } });
  await ctx.addCookies(cookies);
  try {
    const page = ctx.pages()[0] || await ctx.newPage();
    await page.goto('https://mooc1.chaoxing.com/mycourse/studentcourse', { timeout: 45000, waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(4500);
    const s = (page.url().match(/[?&]s=([a-f0-9]+)/) || [])[1];
    if (!s) { log('NEED_RELOGIN'); process.exit(2); }
    await page.goto('http://mooc1-1.chaoxing.com/visit/interaction?s=' + s, { timeout: 45000, waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(4500);
    const target = await page.evaluate((k) => {
      const list = [...document.querySelectorAll('a[href*="stucoursemiddle"]')].map(a => ({ name: (a.innerText || '').trim().replace(/\s+/g, ' '), href: a.href }));
      return list.find(x => x.name.replace(/[《》]/g, '') === k) || null;
    }, KEY);
    if (!target) { log('NO_COURSE'); process.exit(3); }
    await page.goto(target.href, { timeout: 45000, waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(5000);
    await page.evaluate(() => { for (const el of [...document.querySelectorAll('a, li, div, span, p')]) { if ((el.innerText || '').trim() === '作业' && el.offsetParent !== null) { el.click(); return; } } });
    let wf = null;
    for (let i = 0; i < 12; i++) { await page.waitForTimeout(1500); wf = page.frames().find(f => f.url().includes('/work/')); if (wf) break; }
    if (!wf) { log('NO_WORK_FRAME'); process.exit(4); }
    await wf.evaluate((w) => {
      const el = [...document.querySelectorAll('div, li, a, span, p, td')].find(e => (e.innerText || '').trim() === w);
      let ct = el; for (let i = 0; i < 6 && ct; i++, ct = ct.parentElement) { if (ct.getAttribute('onclick') || ct.tagName === 'A') break; } ct.click();
    }, WORK);
    await page.waitForTimeout(9000);
    const wp = ctx.pages().find(p => p.url().includes('dowork')) || page;
    await wp.waitForTimeout(4000);
    await wp.evaluate(() => { [...document.querySelectorAll('button, a, div, span')].forEach(el => { if ((el.innerText || '').trim() === '知道了' && el.offsetParent !== null) { try { el.click(); } catch (e) {} } }); });
    log('答题页:', wp.url().slice(0, 120));
    await wp.evaluate(({b})=>{window.__IMG_B64__=b;}, {b:fsB64(IMG)});

    // 1) 页内 fetch 上传（带 cookie 与 UEditor token）
    const upload = await wp.evaluate(async ({ imgPath, q }) => {
      const inst = UE.instants['ueditorInstant' + (q - 1)];
      const url = inst.getOpt('imageUrl') || inst.getOpt('serverUrl');
      const b64 = window.__IMG_B64__;
      const bin = atob(b64);
      const arr = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      const fd = new FormData();
      fd.append('upfile', new Blob([arr], { type: 'image/png' }), 'answer-sheet.png');
      const res = await fetch(url + (url.includes('?') ? '&' : '?') + 'action=uploadimage', { method: 'POST', body: fd, credentials: 'include' });
      const j = await res.json().catch(() => null);
      return { url: url.slice(0, 100), status: res.status, json: j };
    }, { imgPath: IMG, q: QN }).catch(e => ({ err: e.message }));
    log('上传响应:', JSON.stringify(upload).slice(0, 400));
    if (upload.err || !upload.json || upload.json.state !== 'SUCCESS') { log('上传失败,不插入'); process.exit(6); }
    const imgUrl = upload.json.url;
    log('图片URL:', imgUrl);
    // 2) 插入到第QN题编辑器(清空文字答案,只留图)
    const ins = await wp.evaluate(({ url, q }) => {
      const inst = UE.instants['ueditorInstant' + (q - 1)];
      inst.ready(function () {
        inst.setContent('<p><img src="' + url + '" style="max-width:100%;" /></p>');
        inst.fireEvent('contentChange');
      });
      return true;
    }, { url: imgUrl, q: QN });
    await wp.waitForTimeout(2500);
    const check = await wp.evaluate(({ q }) => {
      const inst = UE.instants['ueditorInstant' + (q - 1)];
      return { html: (inst.getContent() || '').slice(0, 180), text: (inst.getContentTxt() || '').slice(0, 60) };
    }, { q: QN });
    log('插入后编辑器:', JSON.stringify(check));
    // 3) 暂时保存
    const saved = await wp.evaluate(() => {
      const t = [...document.querySelectorAll('a, button, div, span')].find(e => (e.innerText || '').trim() === '暂时保存' && e.offsetParent !== null);
      if (t) { t.click(); return 'OK'; } return 'NO_BUTTON';
    });
    log('暂时保存:', saved);
    await wp.waitForTimeout(4000);
    await wp.screenshot({ path: path.join(OUTDIR, 'q' + QN + '-img-inserted.png'), fullPage: false });
    log('完成 — 未提交');
  } finally { await ctx.close(); }
})().catch(e => { console.error('FATAL:', e.message); process.exit(1); });