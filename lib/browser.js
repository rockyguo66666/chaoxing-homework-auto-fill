'use strict';
/**
 * 浏览器公共层：带登录态地打开学习通，并导航到指定作业的答题页。
 * 之前的脚本各自复制了一遍导航代码，这里收敛成一处。
 */
const fs = require('fs');
const path = require('path');
const C = require('./config');

/** 打开带 cookie 的持久化上下文 */
async function launch(opts) {
  opts = opts || {};
  const { chromium } = require('./playwright');
  if (!fs.existsSync(C.COOKIES)) {
    throw new Error('NEED_RELOGIN: 找不到 ' + C.COOKIES + '，请先执行「cx login」');
  }
  C.ensureHome();
  const channel = C.CHANNEL === 'bundled' ? undefined : C.CHANNEL;
  const ctx = await chromium.launchPersistentContext(C.PROFILE, {
    channel: channel,
    headless: opts.headless !== undefined ? opts.headless : C.HEADLESS,
    viewport: opts.viewport || { width: 1360, height: 900 },
  });
  ctx.addCookies(JSON.parse(fs.readFileSync(C.COOKIES, 'utf8')));
  return ctx;
}

/**
 * 导航到「课程 → 作业 → 作业名」的答题页。
 * 返回 { page, wp, workFrame }，失败返回 { err: '原因' }。
 */
async function openCourseWork(ctx, course, work) {
  const page = ctx.pages()[0] || await ctx.newPage();
  const known = new Set(ctx.pages().map(p => p.url()));
  await page.goto('https://mooc1.chaoxing.com/mycourse/studentcourse',
    { timeout: 45000, waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4500);
  const s = (page.url().match(/[?&]s=([a-f0-9]+)/) || [])[1];
  if (!s) return { err: 'NEED_RELOGIN' };
  await page.goto('http://mooc1-1.chaoxing.com/visit/interaction?s=' + s,
    { timeout: 45000, waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4500);
  const target = await page.evaluate((k) => {
    const nn = t => (t || '').replace(/[《》]/g, '').trim();
    const list = [...document.querySelectorAll('a[href*="stucoursemiddle"]')]
      .map(a => ({ name: (a.innerText || '').trim().replace(/\s+/g, ' '), href: a.href }));
    return list.find(x => nn(x.name) === k) || list.find(x => nn(x.name).includes(k)) || null;
  }, course);
  if (!target) return { err: 'NO_COURSE' };
  await page.goto(target.href, { timeout: 45000, waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(5000);
  await page.evaluate(() => {
    for (const el of [...document.querySelectorAll('a, li, div, span, p')]) {
      if ((el.innerText || '').trim() === '作业' && el.offsetParent !== null) { el.click(); return; }
    }
  });
  let wf = null;
  for (let i = 0; i < 12; i++) {
    await page.waitForTimeout(1500);
    wf = page.frames().find(f => f.url().includes('/work/'));
    if (wf) break;
  }
  if (!wf) return { err: 'NO_WORK_FRAME' };
  await wf.waitForTimeout(2000);
  const go = await wf.evaluate((w) => {
    const nodes = [...document.querySelectorAll('div, li, a, span, p, td')];
    const el = nodes.find(e => (e.innerText || '').trim() === w)
      || nodes.find(e => (e.innerText || '').trim().startsWith(w) && (e.innerText || '').length < w.length + 14);
    if (!el) return 'NOT_FOUND';
    let ct = el;
    for (let i = 0; i < 6 && ct; i++, ct = ct.parentElement) {
      if (ct.getAttribute('onclick') || ct.tagName === 'A') break;
    }
    try { ct.click(); return 'OK'; } catch (e) { return 'ERR'; }
  }, work);
  if (go === 'NOT_FOUND') return { err: 'NO_WORK_ITEM' };
  let wp = null;
  for (let i = 0; i < 20; i++) {
    await page.waitForTimeout(1500);
    const fresh = ctx.pages().filter(p => /dowork|doHomeWorkNew/.test(p.url()) && !known.has(p.url()));
    if (fresh.length) { wp = fresh[fresh.length - 1]; break; }
    if (/dowork|doHomeWorkNew/.test(page.url())) { wp = page; break; }
  }
  if (!wp) return { err: 'NO_ANSWER_PAGE' };
  await wp.waitForTimeout(5000);
  await wp.evaluate(() => {
    [...document.querySelectorAll('button, a, div, span')].forEach(el => {
      if ((el.innerText || '').trim() === '知道了' && el.offsetParent !== null) {
        try { el.click(); } catch (e) { /* 忽略 */ }
      }
    });
  });
  return { page: page, wp: wp, workFrame: wf };
}

/**
 * 找出第 idx 题（0-based）对应的 UEditor 实例下标 k。
 * 注意：实例号 ≠ 题号！一份卷里可能只有 2 个编辑器却有 7 道题，
 * 必须按该题 DOM 里的 iframe[id^=ueditor_] 取 k。
 */
async function editorIndexOf(wp, idx) {
  return wp.evaluate(({ idx }) => {
    const qs = [...document.querySelectorAll('[id^="question"]')]
      .filter(e => /^question\d+$/.test(e.id));
    const q = qs[idx];
    if (!q) return { err: 'NOQ' };
    const ifr = q.querySelector('iframe[id^="ueditor_"]');
    if (!ifr) return { err: 'NO_EDITOR_IN_QUESTION' };
    const k = Number(ifr.id.replace('ueditor_', ''));
    if (!UE.instants['ueditorInstant' + k]) return { err: 'NO_INST_' + k };
    return { k: k };
  }, { idx: idx });
}

module.exports = { launch, openCourseWork, editorIndexOf };
