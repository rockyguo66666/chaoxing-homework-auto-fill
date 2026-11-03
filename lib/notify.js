'use strict';
/**
 * 跨平台通知。
 *  - 设了 CX_NOTIFY_CMD：调用它，参数为「标题 正文 模式(banner|dialog)」
 *  - macOS：osascript display notification（横幅）
 *  - 其他：只打印到 stdout
 */
const { execFileSync } = require('child_process');
const os = require('os');

function notify(title, message, mode) {
  mode = mode || 'banner';
  const custom = process.env.CX_NOTIFY_CMD;
  if (custom) {
    try {
      execFileSync('/bin/sh', ['-c', custom + ' ' + JSON.stringify(title) + ' ' + JSON.stringify(message) + ' ' + mode],
        { stdio: 'inherit' });
      return true;
    } catch (e) {
      console.error('通知命令失败：' + e.message);
    }
  }
  if (os.platform() === 'darwin') {
    try {
      const esc = s => String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
      execFileSync('osascript',
        ['-e', 'display notification "' + esc(message) + '" with title "' + esc(title) + '"'],
        { stdio: 'ignore' });
      return true;
    } catch (e) {
      console.error('通知失败：' + e.message);
    }
  }
  console.log('[提醒] ' + title + ' — ' + message);
  return false;
}

module.exports = { notify };
