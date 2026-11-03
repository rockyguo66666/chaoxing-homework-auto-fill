#!/usr/bin/env node
'use strict';
/**
 * cx —— 学习通作业自动化统一入口（harness）
 *
 *   cx login                     扫码登录，导出 cookies
 *   cx scan                      扫描全部课程未交作业 → result.json
 *   cx list                      打印未交清单（含距截止天数）
 *   cx grab <课程> <作业> [目录]   抓题目：每题截图 + questions.json
 *   cx fill <课程> <作业> <json>  文字答案填入 → 暂时保存
 *   cx img <课程> <作业> <题号> <png>  手写答题纸插图 → 暂时保存
 *   cx mixed <课程> <作业> <choices.json> <images.json>  混合卷一趟做完
 *   cx push [--force] [--dry]     推送待办提醒
 *   cx submit <课程> <作业> --yes  提交作业（危险，需显式 --yes）
 *
 * 默认永远只「暂时保存」，提交要显式 --yes。
 */
const path = require('path');
const { spawnSync } = require('child_process');

const SCRIPTS = path.join(__dirname, '..', 'scripts');

function run(script, args) {
  const r = spawnSync(process.execPath, [path.join(SCRIPTS, script)].concat(args),
    { stdio: 'inherit', env: process.env });
  process.exit(r.status === null ? 1 : r.status);
}

function help() {
  console.log([
    '学习通作业自动化 cx',
    '',
    '  cx login                      扫码登录（会弹出浏览器）',
    '  cx scan                       扫描所有课程未交作业',
    '  cx list                       打印未交清单',
    '  cx grab <课程> <作业> [目录]  抓题目',
    '  cx fill <课程> <作业> <json>  文字答案 → 暂时保存',
    '  cx img <课程> <作业> <题号> <png>  插图 → 暂时保存',
    '  cx mixed <课程> <作业> <c.json> <i.json>  混合卷 → 暂时保存',
    '  cx push [--force] [--dry]      推送待办提醒',
    '  cx sheet <答案.txt> --out <图.png>   把手写答题纸渲染成图片',
    '  cx submit <课程> <作业> --yes 提交作业（危险）',
    '',
    '环境变量：CX_HOME CX_PROFILE CX_COOKIES CX_RESULT CX_OUT CX_CHANNEL CX_HEADLESS',
  ].join('\n'));
}

const argv = process.argv.slice(2);
const cmd = argv[0];
const rest = argv.slice(1);

switch (cmd) {
  case 'login':   run('relogin.js', rest); break;
  case 'scan':    run('scan.js', rest); break;
  case 'list':    run('summarize.js', rest); break;
  case 'grab':    run('grab-qs.js', rest); break;
  case 'fill':    run('fill-save.js', rest); break;
  case 'img':     run('insert-img.js', rest); break;
  case 'mixed':   run('mixed-work.js', rest); break;
  case 'sheet':   run('sheet.js', rest); break;
  case 'push':    run('push.js', rest); break;
  case 'submit':  run('submit.js', rest); break;
  case undefined:
  case '-h':
  case '--help':
  case 'help':    help(); break;
  default:
    console.error('未知命令：' + cmd);
    help();
    process.exit(2);
}