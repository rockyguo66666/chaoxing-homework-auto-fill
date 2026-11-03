#!/usr/bin/env node
// 混合卷: 选择题按显示索引点选 + 计算题插入手写图 -> 暂时保存(绝不提交) -> 关页重开验证
// 用法: node mixed-work.js <课程> <作业名> <choices.json> <images.json>
// choices.json 值: "A"/"B"...按显示顺序; 或 "~文本片段" 按内容匹配(防选项乱序)
const { chromium } = require('../lib/playwright');
const path = require('path'); const fs = require('fs');
const { COOKIES: COOKFILE, PROFILE } = require('../lib/config');
const KEY = process.argv[2], WORK = process.argv[3];
function readJson(p, label) {
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8'));
  } catch (e) {
    console.error(label + ' 不是合法 JSON：' + p + '（' + e.message + '）');
    process.exit(2);
  }
}
const CHOICES = readJson(process.argv[4], 'choices.json');
const IMAGES = readJson(process.argv[5], 'images.json');
const log = (...a) => console.log('[mixed]', ...a);

async function openWork(ctx) {
  const page = ctx.pages()[0] || await ctx.newPage();
  await page.goto('https://mooc1.chaoxing.com/mycourse/studentcourse', { timeout: 45000, waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4500);
  const s = (page.url().match(/[?&]s=([a-f0-9]+)/) || [])[1];
  if (!s) { log('NEED_RELOGIN'); return { err: 'NEED_RELOGIN' }; }
  await page.goto('http://mooc1-1.chaoxing.com/visit/interaction?s=' + s, { timeout: 45000, waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4500);
  const target = await page.evaluate((k) => {
    const nn = t => (t || '').replace(/[《》]/g, '').trim();
    const list = [...document.querySelectorAll('a[href*="stucoursemiddle"]')].map(a => ({ name: (a.innerText || '').trim().replace(/\s+/g, ' '), href: a.href }));
    return list.find(x => nn(x.name) === k) || list.find(x => nn(x.name).includes(k)) || null;
  }, (KEY || '').replace(/[《》]/g, '').trim());
  if (!target) { log('NO_COURSE', KEY); return { err: 'NO_COURSE' }; }
  await page.goto(target.href, { timeout: 45000, waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(5000);
  await page.evaluate(() => { for (const el of [...document.querySelectorAll('a, li, div, span, p')]) { if ((el.innerText || '').trim() === '作业' && el.offsetParent !== null) { el.click(); return; } } });
  let wf = null;
  for (let i = 0; i < 12; i++) { await page.waitForTimeout(1500); wf = page.frames().find(f => f.url().includes('/work/')); if (wf) break; }
  if (!wf) { log('NO_WORK_FRAME'); return { err: 'NO_WORK_FRAME' }; }
  await wf.waitForTimeout(2000);
  const go = await wf.evaluate((w) => {
    const nodes = [...document.querySelectorAll('div, li, a, span, p, td')];
    const el = nodes.find(e => (e.innerText || '').trim() === w) || nodes.find(e => (e.innerText || '').trim().startsWith(w) && (e.innerText || '').length < w.length + 14);
    if (!el) return 'NOT_FOUND';
    let ct = el;
    for (let i = 0; i < 6 && ct; i++, ct = ct.parentElement) { if (ct.getAttribute('onclick') || ct.tagName === 'A') break; }
    try { ct.click(); return 'OK:' + (ct.tagName + '/' + (ct.getAttribute('onclick') || '').slice(0, 12)); } catch (e) { return 'ERR:' + e.message.slice(0, 40); }
  }, WORK);
  log('点开作业:', go);
  let wp = null;
  for (let i = 0; i < 20; i++) {
    await page.waitForTimeout(1500);
    wp = ctx.pages().find(p => /dowork|doHomeWorkNew/.test(p.url())) || null;
    if (wp) break;
    const self = page.url();
    if (/dowork|doHomeWorkNew/.test(self)) { wp = page; break; }
  }
  if (!wp) { log('NO_ANSWER_PAGE', page.url().slice(0, 100)); return { err: 'NO_ANSWER_PAGE' }; }
  await wp.waitForTimeout(5000);
  if (!(await wp.evaluate(() => [...document.querySelectorAll('[id^="question"]')].filter(e => /^question\d+$/.test(e.id)).length))) {
    await wp.bringToFront().catch(() => {});
    await wp.waitForTimeout(5000);
  }
  await wp.evaluate(() => { [...document.querySelectorAll('button, a, div, span')].forEach(el => { if ((el.innerText || '').trim() === '知道了' && el.offsetParent !== null) { try { el.click(); } catch (e) {} } }); });
  await wp.waitForTimeout(1200);
  log('答题页:', wp.url().slice(0, 120));
  return { wp };
}

async function clickChoices(wp, choices) {
  for (const [n, letter] of Object.entries(choices)) {
    const idx = Number(n) - 1;
    const r = await wp.evaluate(({ idx, letter }) => {
      const qs = [...document.querySelectorAll('[id^="question"]')].filter(e => /^question\d+$/.test(e.id));
      const q = qs[idx]; if (!q) return 'NOQ';
      const opts = [...q.querySelectorAll('.answerBg, [class*="answerBg"]')];
      if (!opts.length) return 'NOOPTS';
      // 答案字母按「显示顺序」给出 -> 直接用索引；"~文本" 形式按内容匹配
      let target;
      if (String(letter).startsWith('~')) {
        const want = String(letter).slice(1).trim().toLowerCase();
        target = opts.find(o => (o.innerText || '').replace(/\s+/g, '').toLowerCase().includes(want));
      } else {
        target = opts[String(letter).toUpperCase().charCodeAt(0) - 65];
      }
      if (!target) return 'NOIDX';
      const on = target.getAttribute('aria-checked') === 'true' || /check|cur|selected|active/i.test((target.className || '').toString());
      if (!on) target.click();
      const d = target.querySelector('[data]');
      return (on ? 'already:' : 'clicked:') + String(letter) + '|data=' + (d ? d.getAttribute('data') : '?') + '|txt=' + (target.innerText || '').replace(/\s+/g, ' ').slice(0, 18);
    }, { idx, letter });
    log('Q' + n, String(letter), '=>', r);
    await wp.waitForTimeout(500);
  }
}

async function insertImages(wp, images) {
  for (const [n, imgPath] of Object.entries(images)) {
    const idx = Number(n) - 1;
    // 题号 ≠ UEditor 实例号：按该题 DOM 内的 iframe id 解析真实实例
    const resolved = await wp.evaluate(({ idx }) => {
      const qs = [...document.querySelectorAll('[id^="question"]')].filter(e => /^question\d+$/.test(e.id));
      const q = qs[idx]; if (!q) return { err: 'NOQ' };
      const ifr = q.querySelector('iframe[id^="ueditor_"]');
      if (!ifr) return { err: 'NO_EDITOR_IN_QUESTION' };
      const k = Number(ifr.id.replace('ueditor_', ''));
      const inst = UE.instants['ueditorInstant' + k];
      if (!inst) return { err: 'no inst ' + k };
      const url = inst.getOpt('imageUrl') || inst.getOpt('serverUrl');
      return { k, url };
    }, { idx });
    if (resolved.err) { log('Q' + n + ' 解析编辑器失败', resolved.err); continue; }
    log('Q' + n + ' → ueditorInstant' + resolved.k);
    const b64 = fs.readFileSync(imgPath).toString('base64');
    await wp.evaluate((b) => { window.__IMG_B64__ = b; }, b64);
    const upload = await wp.evaluate(async ({ url }) => {
      const bin = atob(window.__IMG_B64__); const arr = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      const fd = new FormData(); fd.append('upfile', new Blob([arr], { type: 'image/png' }), 'sheet.png');
      const res = await fetch(url + (url.includes('?') ? '&' : '?') + 'action=uploadimage', { method: 'POST', body: fd, credentials: 'include' });
      const j = await res.json().catch(() => null);
      return { status: res.status, json: j };
    }, { url: resolved.url }).catch(e => ({ err: e.message }));
    if (!upload.json || upload.json.state !== 'SUCCESS') { log('Q' + n + ' 上传失败', JSON.stringify(upload).slice(0, 200)); continue; }
    const imgUrl = upload.json.url;
    await wp.evaluate(({ url, k }) => {
      const inst = UE.instants['ueditorInstant' + k];
      inst.ready(function () { inst.setContent('<p><img src="' + url + '" style="max-width:100%;" /></p>'); inst.fireEvent('contentChange'); });
    }, { url: imgUrl, k: resolved.k });
    log('Q' + n + ' 插图 OK', imgUrl.slice(-46));
    await wp.waitForTimeout(1500);
  }
}

async function tempSave(wp) {
  const saved = await wp.evaluate(() => {
    const t = [...document.querySelectorAll('a, button, div, span')].find(e => (e.innerText || '').trim() === '暂时保存' && e.offsetParent !== null && !e.closest('[class*="dialog"], [class*="mask"], .pop'));
    if (t) { t.click(); return 'OK'; } return 'NO_BUTTON';
  });
  log('暂时保存:', saved);
  await wp.waitForTimeout(4000);
}

async function readBack(wp) {
  return wp.evaluate(() => {
    const qs = [...document.querySelectorAll('[id^="question"]')].filter(e => /^question\d+$/.test(e.id));
    return qs.map((q, i) => {
      const opts = [...q.querySelectorAll('.answerBg, [class*="answerBg"]')];
      const selIdx = opts.findIndex(o => o.getAttribute('aria-checked') === 'true' || /check|cur|selected|active/i.test((o.className || '').toString()));
      const ifr = q.querySelector('iframe[id^="ueditor_"]');
      let img = false;
      if (ifr) { const k = Number(ifr.id.replace('ueditor_', '')); const inst = UE.instants['ueditorInstant' + k]; img = inst && /<img/.test(inst.getContent() || ''); }
      return { n: i + 1, sel: selIdx < 0 ? null : String.fromCharCode(65 + selIdx), img };
    });
  });
}

(async () => {
  const cookies = JSON.parse(fs.readFileSync(COOKFILE, 'utf8'));
  let ctx = await chromium.launchPersistentContext(PROFILE, { channel: 'msedge', headless: true, viewport: { width: 1360, height: 900 } });
  await ctx.addCookies(cookies);
  let r = await openWork(ctx);
  if (r.err) { await ctx.close(); process.exit(2); }
  const nq = await r.wp.evaluate(() => [...document.querySelectorAll('[id^="question"]')].filter(e => /^question\d+$/.test(e.id)).length);
  log('题目数:', nq);
  if (nq === 0) { log('GUARD: 答题页无题目,中止不写入'); await ctx.close(); process.exit(4); }
  await clickChoices(r.wp, CHOICES);
  await insertImages(r.wp, IMAGES);
  await tempSave(r.wp);
  await ctx.close();
  await new Promise(res => setTimeout(res, 3000));
  ctx = await chromium.launchPersistentContext(PROFILE, { channel: 'msedge', headless: true, viewport: { width: 1360, height: 900 } });
  await ctx.addCookies(cookies);
  r = await openWork(ctx);
  if (r.err) { log('验证打开失败', r.err); await ctx.close(); process.exit(3); }
  log('重开状态:', JSON.stringify(await readBack(r.wp)));
  await ctx.close();
  log('完成 — 未提交');
})().catch(e => { console.error('FATAL:', e.message); process.exit(1); });