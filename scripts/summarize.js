#!/usr/bin/env node
// 从 result.json 生成人类可读摘要 last-summary.txt(供投递/汇报用)
const fs = require('fs');
const path = require('path');
const { RESULT, SUMMARY } = require('../lib/config');

function main() {
  const raw = JSON.parse(fs.readFileSync(RESULT, 'utf8'));
  const courses = Array.isArray(raw) ? raw : (raw.courses || []);
  const semesterEnd = raw.semesterEnd || '2027-01-17';

  const pending = courses.filter(c => (c.pendingItems || []).length > 0);
  const closedCount = courses.reduce((n, c) => n + ((c.closedItems || []).length), 0);
  const ignoredCount = courses.reduce((n, c) => n + (c.ignoredItems || []).length, 0);

  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const stamp = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;

  const lines = [];
  lines.push('学习通作业检查 · ' + stamp);

  if (pending.length === 0) {
    lines.push('今日学习通无新作业');
  } else {
    for (const c of pending) {
      lines.push(c.course);
      const items = c.items || [];
      for (const text of c.pendingItems) {
        // 兼容旧版 result.json:待批阅不再显示「截止:未知」
        lines.push('  - ' + text.replace(/待批阅 · 截止:未知/, '待批阅(已提交)'));
      }
      // 过期但仍可作答的,补一行原截止时间说明
      for (const it of items) {
        if (it.deadlineSource === 'semester_end') {
          const orig = it.originalDeadline ? `原截止 ${it.originalDeadline}` : '原截止已过';
          lines.push(`    ↳ ${it.name} ${orig},答题页仍开放,按学期末(${semesterEnd})计`);
        }
      }
    }
  }
  if (closedCount > 0) lines.push(`(另有 ${closedCount} 条过期且答题页已关闭,不再提醒)`);
  if (ignoredCount > 0) lines.push(`(本学期起已忽略上学期遗留作业 ${ignoredCount} 条,不再提醒)`);

  fs.writeFileSync(SUMMARY, lines.join('\n'));
  console.log(lines.join('\n'));
}

main();
