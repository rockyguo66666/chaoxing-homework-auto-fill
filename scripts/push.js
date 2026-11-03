#!/usr/bin/env node
// 学习通待办推送 —— 读 openclaw 扫描产物 result.json,推送 macOS 通知
// 用法: node chaoxing-push.js [--force] [--dry]
// 登录态归 openclaw 所有,本脚本只读文件,不碰浏览器。
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const { DIR, RESULT, STATE, MAX_AGE_H } = require('../lib/config');
const { notify } = require('../lib/notify');
const FORCE = process.argv.includes('--force');
const DRY = process.argv.includes('--dry');
 // result.json 超过这个小时数视为过期,不推送(防拿旧数据说事)

function pad(n) { return String(n).padStart(2, '0'); }
function stamp(d) { return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`; }

function loadState() { try { return JSON.parse(fs.readFileSync(STATE, 'utf8')); } catch { return { days: 0, lastScanAt: null, lastDate: null }; } }

// 把 "练习作业4 未交 · 截止:10-31 22:59" 解析成结构化条目
function parseItem(text) {
  const m = String(text).match(/^(.+?)\s+(未交|待批阅)\(?.*$/);
  const name = m ? m[1] : String(text);
  const deadline = (String(text).match(/截止[:：]\s*([^·]+)/) || [])[1];
  const submitted = /待批阅/.test(text);
  return { name, deadline: deadline ? deadline.trim() : null, submitted };
}
// 截止日期转成天数(仅为排序/提醒用;学期末截止视为远期)
function deadlineDays(deadline, semesterEnd) {
  if (!deadline) return 999;
  if (/学期末/.test(deadline)) return 999;
  const m = deadline.match(/(\d{1,2})-(\d{1,2})/);
  if (!m) return 998;
  const now = new Date();
  const d = new Date(now.getFullYear(), Number(m[1]) - 1, Number(m[2]), 23, 59);
  return Math.round((d - now) / 86400000);
}

function main() {
  if (!fs.existsSync(RESULT)) { console.error('NO_RESULT'); process.exit(2); }
  const raw = JSON.parse(fs.readFileSync(RESULT, 'utf8'));
  const courses = Array.isArray(raw) ? raw : (raw.courses || []);
  const semesterEnd = raw.semesterEnd || '';
  const scanAt = raw.checkedAt ? new Date(raw.checkedAt) : (fs.statSync(RESULT).mtime);
  const ageH = (Date.now() - scanAt.getTime()) / 3600000;
  if (ageH > MAX_AGE_H) { console.log(`SCAN_STALE ${ageH.toFixed(1)}h — 不推送,先跑 check-homework.js`); process.exit(3); }

  const st = loadState();
  const today = stamp(new Date()).split(' ')[0];
    // 幂等闸：同一份扫描结果 12h 内只推一次（08:30 主任务推过，08:40 launchd 兜底就自动跳过）
  if (st.lastScanAt === raw.checkedAt && st.lastPushTs && (Date.now() - st.lastPushTs) < 12 * 3600 * 1000) {
    console.log('SKIP: 这份扫描(' + raw.checkedAt + ')已在 ' + new Date(st.lastPushTs).toLocaleString('zh-CN') + ' 推送过,不重复打扰');
    return;
  }
if (!FORCE && st.lastDate === today && !process.argv.includes('--daily')) {
    // 同一天不重复推(除非 --force);扫描更新了也会重推增量
  }

  // 汇总:待办(未交)+ 待批阅(已交等成绩)
  const pending = [], awaiting = [];
  for (const c of courses) {
    for (const text of (c.pendingItems || [])) {
      const it = parseItem(text);
      const d = deadlineDays(it.deadline, semesterEnd);
      const row = { course: c.course, ...it, days: d };
      if (it.submitted) awaiting.push(row); else pending.push(row);
    }
  }
  pending.sort((a, b) => a.days - b.days);

  const lines = [];
  if (pending.length === 0) {
    lines.push('学习通: 没有未交作业 ✅');
  } else {
    lines.push(`学习通未交 ${pending.length} 项(扫描 ${stamp(scanAt)}):`);
    for (const p of pending) {
      const dtag = p.days <= 0 ? '今天截止!' : p.days <= 3 ? `还剩 ${p.days} 天` : (p.days >= 900 ? '学期末' : `还剩 ${p.days} 天`);
      lines.push(`· ${p.course} / ${p.name} — ${dtag}${p.deadline ? ' (' + p.deadline + ')' : ''}`);
    }
  }
  if (awaiting.length) lines.push(`(另有 ${awaiting.length} 项已提交待批阅)`);

  const title = pending.length ? `学习通 · 未交 ${pending.length} 项` : '学习通 · 作业已清空';
  const body = pending.length
    ? pending.slice(0, 4).map(p => `${p.name}@${p.course}`).join(' | ') + (pending.length > 4 ? ` 等 ${pending.length} 项` : '')
    : '没有未交作业';

  console.log(lines.join('\n'));
  if (DRY) { console.log('\n[DRY] 通知标题:', title, '| 正文:', body); return; }

  // Rocky 规则(2026-10-26):普通待办提醒只用 banner,严禁弹窗
  notify(title, body, 'banner');
  fs.writeFileSync(STATE, JSON.stringify({ lastDate: today, lastScanAt: raw.checkedAt, lastPushTs: Date.now(), days: (st.days || 0) + 1 }, null, 2));
  console.log('\n推送完成 →', title);
}

main();