#!/usr/bin/env node
'use strict';
/**
 * 提交作业（不可逆）。
 * 必须显式加 --yes，否则只打印将要做的动作并退出。
 * 用法: node submit.js <课程> <作业> --yes
 */
const path = require('path');
const fs = require('fs');
const C = require('../lib/config');
const { launch, openCourseWork } = require('../lib/browser');

const COURSE = process.argv[2];
const WORK = process.argv[3];
const YES = process.argv.includes('--yes');

if (!COURSE || !WORK) {
  console.error('用法: node submit.js <课程> <作业> --yes');
  process.exit(2);
}
if (!YES) {
  console.log('这是不可逆的提交操作。确认无误后请加 --yes 重新执行：');
  console.log('  cx submit ' + COURSE + ' ' + WORK + ' --yes');
  process.exit(3);
}

(async () => {
  const ctx = await launch();
  const r = await openCourseWork(ctx, COURSE, WORK);
  if (r.err) { console.error(r.err); process.exit(4); }
  const wp = r.wp;
  await wp.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await wp.waitForTimeout(1500);
  const clicked = await wp.evaluate(() => {
    const el = [...document.querySelectorAll('a, button, div, span')].find(e =>
      (e.innerText || '').trim() === '提交' && e.offsetParent !== null
      && !e.closest('[class*="mask"],[class*="dialog"]'));
    if (el) { el.click(); return 'OK'; }
    return 'NO_BTN';
  });
  console.log('点提交：' + clicked);
  await wp.waitForTimeout(3000);
  const confirmed = await wp.evaluate(() => {
    for (const d of [...document.querySelectorAll('[class*="dialog"],[class*="mask"],[class*="confirm"]')]) {
      if (d.offsetParent === null) continue;
      const b = [...d.querySelectorAll('a, button, div, span')].find(e =>
        ['确定', '确认提交', '提交', '是', 'OK'].includes((e.innerText || '').trim())
        && e.offsetParent !== null);
      if (b) { b.click(); return 'CONFIRMED'; }
    }
    return 'NO_DIALOG';
  });
  console.log('二次确认：' + confirmed);
  await wp.waitForTimeout(6000);
  const body = await wp.evaluate(() => document.body.innerText.replace(/\n+/g, ' | ').slice(0, 300));
  console.log('提交后：' + body);
  const shot = path.join(C.OUT, 'submit-' + Date.now() + '.png');
  fs.mkdirSync(C.OUT, { recursive: true });
  await wp.screenshot({ path: shot, fullPage: true });
  console.log('回执截图：' + shot);
  await ctx.close();
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
