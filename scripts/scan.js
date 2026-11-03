#!/usr/bin/env node
// 学习通作业自动检查脚本
// 流程:登录态(cookies.json) → 课程列表 → 每门课进课程页 → 点"作业"菜单 → 解析作业列表
// 每条作业输出:作业名 / 状态 / 截止时间
//   未过期:截止 = 当前时间 + 列表里的「剩余X天X小时X分钟」
//   已过期(列表无剩余时间):打开答题页探测
//     - 能进且可提交 → 保留,截止日期改为学期末(SEMESTER_END),并记录原截止时间
//     - 进不去/已关闭 → 丢弃(计入 closedCount)
// 用法: node check-homework.js [--no-probe] [--only=<课程关键字>]
const { chromium } = require('../lib/playwright');
const path = require('path');
const fs = require('fs');

const { PROFILE } = require('../lib/config');
const { COOKIES: COOKIE_FILE } = require('../lib/config');
const { RESULT: OUT_FILE } = require('../lib/config');
const { IGNORE: IGNORE_FILE } = require('../lib/config');

// 学期末(第19周末 2027-01-11 ~ 2027-01-17)
const SEMESTER_END = '2027-01-17';

const ARGS = process.argv.slice(2);
const NO_PROBE = ARGS.includes('--no-probe');
const ONLY = (ARGS.find(a => a.startsWith('--only=')) || '').split('=')[1] || null;

// 排除清单:上学期遗留作业,模糊匹配(课程名+作业名均包含关系)
let IGNORED = [];
try { IGNORED = JSON.parse(fs.readFileSync(IGNORE_FILE, 'utf8')).ignored || []; } catch (e) { console.log('WARN: ignore-list.json 读取失败', e.message); }
function isIgnored(course, workText) {
  return IGNORED.some(ig => course.includes(ig.course) && (workText || '').includes(ig.work));
}

const pad = n => String(n).padStart(2, '0');
function fmt(d) { return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`; }
function fmtFull(d) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; }

// "剩余2天3小时5分钟" → ms
function parseRemainingMs(t) {
  let ms = 0;
  const d = /(\d+)\s*天/.exec(t); if (d) ms += +d[1] * 86400000;
  const h = /(\d+)\s*小时/.exec(t); if (h) ms += +h[1] * 3600000;
  const m = /(\d+)\s*分钟/.exec(t); if (m) ms += +m[1] * 60000;
  return ms;
}

// "作答时间:09-28 15:49至10-07 23:00" → 截止 Date(补年份)
function parseAnswerWindow(txt) {
  const m = /至\s*(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})/.exec(txt || '');
  if (!m) return null;
  const now = new Date();
  const d = new Date(now.getFullYear(), +m[1] - 1, +m[2], +m[3], +m[4], 0, 0);
  if (d - now > 183 * 86400000) d.setFullYear(d.getFullYear() - 1);   // 跨年回退
  if (now - d > 549 * 86400000) d.setFullYear(d.getFullYear() + 1);    // 前一年 12 月作业
  return d;
}

async function main() {
  if (!fs.existsSync(COOKIE_FILE)) { console.log('NEED_RELOGIN: cookies.json 不存在'); process.exit(2); }
  const cookies = JSON.parse(fs.readFileSync(COOKIE_FILE, 'utf8'));
  const ctx = await chromium.launchPersistentContext(PROFILE, {
    channel: (require('../lib/config').CHANNEL === 'bundled' ? undefined : require('../lib/config').CHANNEL),
    headless: require('../lib/config').HEADLESS, viewport: { width: 1360, height: 900 },
  });
  await ctx.addCookies(cookies);
  const page = ctx.pages()[0] || await ctx.newPage();

  // 1. 课程列表
  await page.goto('https://mooc1.chaoxing.com/mycourse/studentcourse', { timeout: 45000, waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
  const u1 = page.url();
  const s = (u1.match(/[?&]s=([a-f0-9]+)/) || [])[1];
  if (!s) {
    if (u1.includes('login')) { console.log('NEED_RELOGIN: 登录态失效'); await ctx.close(); process.exit(2); }
    console.log('NO_SESSION'); await ctx.close(); process.exit(3);
  }
  await page.goto('http://mooc1-1.chaoxing.com/visit/interaction?s=' + s, { timeout: 45000, waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);

  let courses = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll('a[href*="stucoursemiddle"]').forEach(a => {
      const t = (a.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 40);
      const cid = (a.href.match(/courseid=(\d+)/) || [])[1];
      const clazz = (a.href.match(/clazzid=(\d+)/) || [])[1];
      const cpi = (a.href.match(/cpi=(\d+)/) || [])[1];
      if (t && cid && !out.some(c => c.courseid === cid && c.clazzid === clazz)) {
        out.push({ name: t, courseid: cid, clazzid: clazz, cpi: cpi, url: a.href });
      }
    });
    return out;
  }).catch(() => []);
  if (ONLY) courses = courses.filter(c => c.name.includes(ONLY));
  console.log('课程数:', courses.length);

  const results = [];
  for (const c of courses) {
    const row = { course: c.name, courseid: c.courseid, clazzid: c.clazzid, items: [], error: null };
    try {
      // 2. 进课程页
      await page.goto(c.url, { timeout: 45000, waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(4500);
      const enc = (page.url().match(/[?&]enc=([a-f0-9]+)/) || [])[1];
      if (!enc) { row.error = 'no_enc:' + page.url().slice(0, 100); results.push(row); continue; }

      // 3. 点"作业"菜单,等 iframe
      await page.evaluate(() => {
        const all = [...document.querySelectorAll('a, li, div, span, p')];
        for (const el of all) {
          if ((el.innerText || '').trim() === '作业' && el.offsetParent !== null) { el.click(); return; }
        }
      });
      let workFrame = null;
      for (let i = 0; i < 10; i++) {
        await page.waitForTimeout(1500);
        workFrame = page.frames().find(f => f.url().includes('/work/'));
        if (workFrame) break;
      }
      if (!workFrame) { row.error = 'no_work_frame'; results.push(row); continue; }
      await page.waitForTimeout(2500);

      // 4. 结构化解析列表行
      const raw = await workFrame.evaluate(() => {
        const body = document.body ? document.body.innerText.replace(/\n{3,}/g, '\n') : '';
        const lis = [...document.querySelectorAll('li')].filter(li => {
          const t = (li.innerText || '').trim();
          if (!t || t.length > 300) return false;
          if (!/未交|待批阅|已完成|未完成/.test(t)) return false;
          if (/^(全部|已完成|未完成)$/.test(t)) return false;   // 筛选项
          return !!li.querySelector('.right-content, .status');
        });
        const items = lis.map(li => {
          const nameEl = li.querySelector('.right-content p.overHidden2') || li.querySelector('.right-content p');
          const statusEl = li.querySelector('.status');
          const timeEl = li.querySelector('.time');
          return {
            name: nameEl ? (nameEl.innerText || '').trim().replace(/\s+/g, ' ') : '',
            status: statusEl ? (statusEl.innerText || '').trim() : '',
            timeText: timeEl ? (timeEl.innerText || '').trim().replace(/\s+/g, ' ') : '',
            notOver: !!(timeEl && /notOver/.test(timeEl.className || '')),
            url: li.getAttribute('data') || '',
          };
        }).filter(it => it.name);
        return { body: body.slice(0, 3000), items };
      });

      const isEmpty = raw.body.includes('暂无作业') || raw.body.includes('没有作业');
      row.empty = isEmpty;

      for (const it of raw.items) {
        const label = (it.status || '') + (it.timeText ? ' ' + it.timeText : '');
        if (isIgnored(c.name, it.name + ' ' + it.status)) {
          row.ignoredItems = row.ignoredItems || [];
          row.ignoredItems.push(it.name + ' ' + it.status);
          continue;
        }
        if (it.status === '已完成') continue;

        const rec = { name: it.name, status: it.status, taskUrl: it.url || null };

        if (it.notOver && it.timeText) {
          // 未过期:由剩余倒推截止时间
          const ms = parseRemainingMs(it.timeText);
          const dl = ms > 0 ? new Date(Date.now() + ms) : null;
          rec.expired = false;
          rec.remainText = it.timeText;
          rec.deadline = dl ? fmt(dl) : null;
          rec.deadlineFull = dl ? fmtFull(dl) : null;
          rec.deadlineSource = 'countdown';
          row.items.push(rec);
          continue;
        }

        // 无剩余时间 → 已过期
        rec.expired = true;
        rec.remainText = null;

        if (!it.url || it.status === '待批阅') {
          // 待批阅=已提交等批改,不探测;无链接也无法探测
          rec.deadline = null;
          rec.deadlineSource = 'unknown';
          rec.accessible = null;
          row.items.push(rec);
          continue;
        }

        if (NO_PROBE) {
          rec.deadline = null;
          rec.deadlineSource = 'expired_unprobed';
          rec.accessible = null;
          row.items.push(rec);
          continue;
        }

        // 探测答题页
        let probe = { accessible: null, originalDeadline: null, reason: null };
        let p2 = null;
        try {
          p2 = await ctx.newPage();
          await p2.goto(it.url, { timeout: 50000, waitUntil: 'domcontentloaded' });
          await p2.waitForTimeout(5000);
          const info = await p2.evaluate(() => {
            const txt = document.body ? document.body.innerText.replace(/\n{2,}/g, '\n') : '';
            const btns = [...document.querySelectorAll('button, a, input[type=button], input[type=submit]')]
              .filter(el => el.offsetParent !== null).map(el => (el.innerText || el.value || '').trim());
            return {
              url: location.href,
              qCount: document.querySelectorAll('[id^="question"]').length,
              hasSubmit: btns.some(t => /提交/.test(t)),
              hasEnded: /已结束|已截止|作业已关闭|不能提交|提交时间已过|已过期|时间已结束|无法作答/.test(txt),
              window: (txt.match(/作答时间[:：][^\n]{0,60}/) || [])[0] || '',
              text: txt.slice(0, 600),
            };
          });
          const isDowork = /work\/dowork/.test(info.url);
          const acc = isDowork && info.qCount > 0 && info.hasSubmit && !info.hasEnded;
          probe.accessible = acc;
          probe.originalDeadline = parseAnswerWindow(info.window);
          probe.reason = acc ? 'ok' : (!isDowork ? 'not_dowork:' + info.url.slice(0, 60) : info.hasEnded ? 'ended' : 'no_form:q=' + info.qCount + ',submit=' + info.hasSubmit);
        } catch (e) {
          probe.accessible = false;
          probe.reason = 'probe_err:' + e.message.slice(0, 60);
        } finally {
          if (p2) await p2.close().catch(() => {});
        }

        rec.accessible = probe.accessible;
        rec.originalDeadline = probe.originalDeadline ? fmt(probe.originalDeadline) : null;
        rec.probeReason = probe.reason;
        if (probe.accessible) {
          // 过期但仍可作答 → 保留,截止日期改为学期末
          rec.deadline = SEMESTER_END;
          rec.deadlineFull = SEMESTER_END;
          rec.deadlineSource = 'semester_end';
        } else {
          rec.deadline = null;
          rec.deadlineSource = 'closed';
          rec.closed = true;
        }
        row.items.push(rec);
      }

      row.pendingItems = row.items.filter(x => !x.closed).map(x => {
        if (x.status === '待批阅') return `${x.name} 待批阅(已提交)`;
        const dl = x.deadlineSource === 'semester_end' ? `截止:学期末(${SEMESTER_END})`
          : x.deadline ? `截止:${x.deadline}` : '截止:未知';
        return `${x.name} ${x.status} · ${dl}`;
      });
      row.closedItems = row.items.filter(x => x.closed).map(x => `${x.name} ${x.status} · 已关闭不可答`);
      results.push(row);
    } catch (e) {
      row.error = e.message.slice(0, 120);
      results.push(row);
    }
  }

  const out = { checkedAt: new Date().toISOString(), semesterEnd: SEMESTER_END, courses: results };
  fs.writeFileSync(OUT_FILE, JSON.stringify(out, null, 2));

  console.log('=== RESULT ===');
  results.forEach(r => {
    console.log(`课程: ${r.course}${r.error ? ' [ERR:' + r.error + ']' : ''}`);
    (r.pendingItems || []).forEach(t => console.log('  待办: ' + t));
    (r.closedItems || []).forEach(t => console.log('  [已关闭] ' + t));
    if (r.ignoredItems && r.ignoredItems.length) console.log('  [已忽略上学期] ' + r.ignoredItems.join(' | '));
    if (!r.error && !(r.pendingItems || []).length && !(r.closedItems || []).length) console.log('  (无作业)');
  });
  await ctx.close();
}

main().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
