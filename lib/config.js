'use strict';
/**
 * 统一配置：所有路径都从这里出，改成你自己的目录只需设 CX_HOME。
 *
 *   CX_HOME       默认 ~/.chaoxing-homework（登录态、扫描结果、忽略清单都放这）
 *   CX_PROFILE    浏览器用户目录（默认 $CX_HOME/profile）
 *   CX_COOKIES    cookie 文件（默认 $CX_HOME/cookies.json）
 *   CX_RESULT     扫描结果（默认 $CX_HOME/result.json）
 *   CX_IGNORE     忽略清单（默认 $CX_HOME/ignore-list.json）
 *   CX_OUT        产物目录（默认 $CX_HOME/runs）
 *   CX_CHANNEL    浏览器 msedge|chrome|bundled（默认 msedge）
 *   CX_HEADLESS   0 表示有头模式（扫码登录用）
 *   CX_NOTIFY_CMD 自定义通知命令，形如 "notify.sh"，收到 "标题 正文 模式" 三个参数
 */
const os = require('os');
const path = require('path');
const fs = require('fs');
const { execFileSync } = require('child_process');

const HOME = process.env.CX_HOME || path.join(os.homedir(), '.chaoxing-homework');
const PROFILE = process.env.CX_PROFILE || path.join(HOME, 'profile');
const COOKIES = process.env.CX_COOKIES || path.join(HOME, 'cookies.json');
const RESULT = process.env.CX_RESULT || path.join(HOME, 'result.json');
const IGNORE = process.env.CX_IGNORE || path.join(HOME, 'ignore-list.json');
const OUT = process.env.CX_OUT || path.join(HOME, 'runs');
const STATE = process.env.CX_STATE || path.join(HOME, 'push-state.json');
const SUMMARY = path.join(HOME, 'last-summary.txt');
const CHANNEL = process.env.CX_CHANNEL || 'msedge';
const HEADLESS = process.env.CX_HEADLESS !== '0';
const MAX_AGE_H = Number(process.env.CX_MAX_AGE_H || 26);

function ensureHome() {
  fs.mkdirSync(HOME, { recursive: true });
  fs.mkdirSync(path.dirname(PROFILE), { recursive: true });
  return HOME;
}

/** 解析 playwright：CX_PLAYWRIGHT 指定的路径 → 本地 node_modules → 全局安装 */
function loadPlaywright() {
  const hint = process.env.CX_PLAYWRIGHT;
  if (hint) {
    try { return require(hint); } catch (e) {
      throw new Error('CX_PLAYWRIGHT 指定的 playwright 加载失败：' + e.message);
    }
  }
  try { return require('playwright'); } catch (_) { /* 继续找全局 */ }
  try {
    const root = execFileSync('npm root -g', { encoding: 'utf8' }).trim();
    return require(path.join(root, 'playwright'));
  } catch (_) { /* 继续找其他位置 */ }
  const guesses = [
    path.join(HOME, 'node_modules', 'playwright'),
    path.join(process.cwd(), 'node_modules', 'playwright'),
  ];
  for (const g of guesses) {
    try { return require(g); } catch (_) { /* 继续 */ }
  }
  throw new Error('找不到 playwright：请执行 npm install playwright，或设置 CX_PLAYWRIGHT 指向已安装的 playwright');
}

module.exports = {
  HOME, DIR: HOME, PROFILE, COOKIES, RESULT, IGNORE, OUT, STATE, SUMMARY,
  CHANNEL, HEADLESS, MAX_AGE_H, ensureHome, loadPlaywright,
};
