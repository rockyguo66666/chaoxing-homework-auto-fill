#!/usr/bin/env node
'use strict';
/**
 * 环境自检：把「能不能跑」这件事一次说清。
 *   node scripts/doctor.js
 */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const C = require('../lib/config');

function ok(t) { console.log('  [OK]   ' + t); }
function warn(t) { console.log('  [注意] ' + t); }
function bad(t) { console.log('  [缺]   ' + t); }

console.log('学习通作业助手 · 环境自检');
console.log('');
console.log('配置目录: ' + C.HOME);

// node / playwright
let pw = null;
try { pw = require('../lib/playwright'); ok('playwright 已就绪'); }
catch (e) { bad('playwright 未安装：cd ' + path.join(__dirname, '..') + ' && npm install'); }

if (pw) {
  if (C.CHANNEL === 'bundled') {
    const p = pw.chromium.executablePath();
    if (p && fs.existsSync(p)) ok('自带 Chromium 已下载：' + p);
    else warn('自带 Chromium 未下载：执行 npx playwright install chromium');
  } else {
    warn('使用系统浏览器通道 ' + C.CHANNEL + '（若本机没装该浏览器会启动失败，可改 CX_CHANNEL=bundled）');
  }
}

// 登录态
if (fs.existsSync(C.COOKIES)) {
  try {
    const n = JSON.parse(fs.readFileSync(C.COOKIES, 'utf8')).length;
    ok('登录 cookie 已存在（' + n + ' 条）：' + C.COOKIES);
  } catch (e) { bad('cookie 文件损坏：' + C.COOKIES + '，请重跑 node scripts/relogin.js'); }
} else {
  bad('尚未登录：请执行 node scripts/relogin.js（扫码）');
}
if (fs.existsSync(C.PROFILE)) ok('浏览器用户目录：' + C.PROFILE);
else warn('浏览器用户目录还不存在，首次登录后会自动创建');

// 扫描结果
if (fs.existsSync(C.RESULT)) {
  const raw = JSON.parse(fs.readFileSync(C.RESULT, 'utf8'));
  const ageH = (Date.now() - new Date(raw.checkedAt).getTime()) / 3600000;
  const n = (raw.courses || []).reduce((a, c) => a + ((c.pendingItems || []).filter(x => /未交/.test(x) && !/已关闭/.test(x)).length), 0);
  if (ageH <= C.MAX_AGE_H) ok('扫描结果新鲜（' + ageH.toFixed(1) + ' 小时前，' + n + ' 项未交）');
  else warn('扫描结果已过期（' + ageH.toFixed(1) + ' 小时），请重新跑 node scripts/scan.js');
} else {
  warn('还没有扫描结果：node scripts/scan.js');
}

// Python 渲染依赖
let py = null;
for (const c of ['python3', 'python']) {
  const r = spawnSync(c, ['-c', 'import numpy, PIL, fontTools'], { stdio: 'ignore' });
  if (r.status === 0) { py = c; break; }
}
if (py) ok('Python 渲染依赖齐全（' + py + '）');
else warn('系统 python 缺 numpy/Pillow/fontTools；出图时 cx sheet 会自动建 venv 安装（需联网）');

console.log('');
console.log('提示：cx sheet / node scripts/sheet.js 用于把手写答题纸渲染成图片');
