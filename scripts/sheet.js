#!/usr/bin/env node
'use strict';
/**
 * 手写答题纸渲染（调用打包进来的 handwriting-homework 技能）。
 * 首次运行会自动建一个本地 venv 并装 numpy / Pillow / fontTools，
 * 用户不需要自己准备 Python 依赖。
 *
 * 用法: node scripts/sheet.js <答案.txt> --out <输出.png> [--preset 娃娃体] [--title 标题]
 */
const path = require('path');
const fs = require('fs');
const { spawnSync } = require('child_process');
const C = require('../lib/config');

const SKILL = path.join(__dirname, '..', 'skills', 'handwriting-homework');
const PY = path.join(SKILL, 'scripts', 'answer_sheet.py');
const VENV = process.env.CX_VENV || path.join(SKILL, '.venv');

function have(cmd, args) {
  const r = spawnSync(cmd, args, { stdio: 'ignore' });
  return r.status === 0;
}

/** 找一个能用的 python3 */
function findPython() {
  for (const c of (process.env.CX_PYTHON ? [process.env.CX_PYTHON] : ['python3', 'python'])) {
    if (have(c, ['-c', 'import sys'] )) return c;
  }
  return null;
}

/** 系统 python 是否已经装了渲染所需的依赖 */
function pythonHasDeps(cmd) {
  const r = spawnSync(cmd, ['-c', 'import numpy, PIL, fontTools'], { stdio: 'ignore' });
  return r.status === 0;
}

/** venv 里的 python 是否已装好依赖 */
function venvPython() {
  const p = process.platform === 'win32'
    ? path.join(VENV, 'Scripts', 'python.exe')
    : path.join(VENV, 'bin', 'python');
  if (!fs.existsSync(p)) return null;
  const ok = spawnSync(p, ['-c', 'import numpy, PIL, fontTools'], { stdio: 'ignore' });
  return ok.status === 0 ? p : null;
}

/** 首次运行：建 venv 装依赖 */
function bootstrap(python) {
  console.log('[sheet] 首次运行，准备 Python 依赖（约 1 分钟，只需一次）…');
  const v = spawnSync(python, ['-m', 'venv', VENV], { stdio: 'inherit' });
  if (v.status !== 0) {
    console.error('[sheet] 创建虚拟环境失败。若不想用 venv，可自行装好 numpy/Pillow/fontTools 后设 CX_PYTHON 指向你的 python。');
    process.exit(3);
  }
  const vpy = process.platform === 'win32'
    ? path.join(VENV, 'Scripts', 'python.exe')
    : path.join(VENV, 'bin', 'python');
  console.log('[sheet] 安装 numpy / Pillow / fontTools …');
  const pi = spawnSync(vpy, ['-m', 'pip', 'install', '--quiet', 'numpy', 'Pillow', 'fontTools'], { stdio: 'inherit' });
  if (pi.status !== 0) {
    console.error('[sheet] pip 安装失败（需要能访问 PyPI）。可自行装好依赖后设 CX_PYTHON 指向你的 python。');
    process.exit(3);
  }
  const py = venvPython();
  if (!py) {
    console.error('[sheet] 依赖安装未完成。可手动执行：'
      + path.join(VENV, 'bin', 'python')
      + ' -m pip install numpy Pillow fontTools');
    process.exit(3);
  }
  return py;
}

const argv = process.argv.slice(2);
const qa = argv[0];
if (!qa || !fs.existsSync(qa)) {
  console.error('用法: cx sheet <答案.txt> --out <输出.png> [--preset 名字] [--title 标题]');
  process.exit(2);
}

let py = null;
if (process.env.CX_PYTHON) {
  py = pythonHasDeps(process.env.CX_PYTHON) ? process.env.CX_PYTHON : null;
  if (!py) {
    console.error('[sheet] CX_PYTHON 指向的 python 缺少 numpy/Pillow/fontTools，请先装上。');
    process.exit(3);
  }
} else {
  // 系统 python 已带依赖就直接用，省掉建 venv 与联网下载
  const sys = findPython();
  if (sys && pythonHasDeps(sys)) {
    py = sys;
  } else {
    py = venvPython();
    if (!py) {
      if (!sys) {
        console.error('[sheet] 找不到 python3。请安装 Python 3.8+，或设 CX_PYTHON 指向你的 python。');
        process.exit(3);
      }
      py = bootstrap(sys);
    }
  }
}

const extra = argv.slice(1);
const r = spawnSync(py, [PY, '--qa', qa].concat(extra), { stdio: 'inherit', env: process.env });
process.exit(r.status === null ? 1 : r.status);