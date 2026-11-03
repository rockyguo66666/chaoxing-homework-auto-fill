# 踩坑清单

## 登录与浏览器

- **单实例锁**：Playwright 持久化上下文被强杀后，`SingletonLock` 会残留，
  下次启动报「ProcessSingleton」错误。处理：
  `pkill -f "user-data-dir=.*profile"` 然后删掉 profile 目录下的 `SingletonLock`。
- **NEED_RELOGIN**：脚本判断依据是课程页 URL 里有没有 `s=` 参数；
  没有就是登录态掉了，应让用户扫码重登，脚本不要尝试登录。
- **channel 选择**：msedge / chrome 在不同机器上不一定装了；
  用 `CX_CHANNEL=bundled` 走 Playwright 自带 Chromium 最保险。

## 导航

- 作业列表在 iframe 里（URL 含 `/work/`），不是顶层页面。
- 点作业用 `goTask(li)` 会开**新标签页**，必须轮询 `ctx.pages()` 等它出现；
  固定 sleep 容易拿到课程页而不是答题页。
- 作业名匹配要容错：优先全等，再 `startsWith` 且长度差小于阈值。

## 填答

- **编辑器实例号 ≠ 题号**。这是最容易错的一处：一份卷里可能只有 2 个 UEditor 实例
  却有 7 道题。正确做法是在题目 DOM 里找 `iframe[id^="ueditor_"]`，
  取它的数字下标作为 `ueditorInstant` 的编号。
- 选择题：平台会打乱选项的显示顺序而 `data` 字母不变，所以要按**显示顺序**点。
  判断题别用字母（A=对、B=错），用文字匹配更稳。
- 图片：页内 `fetch` UEditor 的 `imageUrl` 上传（带 cookie 与 token），
  拿到 ananas URL 后 `setContent` 写入编辑器。
  直接 `curl` ananas 地址会被防盗链挡（返回 HTML 或空）。
- 「暂时保存」是真落服务端：POST `addStudentWorkNewWeb` 返回 200，
  重开作业仍在。别把「保存后页面没跳转」当成失败。

## 验证

- 写完必须**关掉浏览器重开**再读回，否则你看到的只是内存里的状态。
- 判定「有没有插图」时只读编辑器内容（`instants.getContent()`），
  因为题干里的矩阵图也是 `<img>`，整题 innerHTML 会误判。
- 断言选项时用显示索引（DOM 里 `.answerBg` 的顺序），别用 `data` 属性。

## 读题（题干是照片时）

- 题干常是学生/老师拍的手机照片，页面上的缩略图分辨率低。
  DOM 里 `img[data-original]` 或 `img[src]` 里换成 `/star3/origin/` 的地址即原图。
- 原图要用**页面内 fetch** 下载（带 cookie），外部 curl 会被防盗链挡。
- 照片可能是 90°/180° 侧着的，先做旋转再读；同一张图用不同旋转各读一次，
  哪一版文字正立就用哪一版。
- 矩阵/公式图是懒加载，`naturalWidth === 0` 说明还没加载；
  先 `scrollIntoView` 再等 `onload`，否则截到空白。
- 读不清就换模型交叉读，或直接问用户，别猜数值。

## 通知

- macOS 用 `terminal-notifier`；横幅（banner）不打断，弹窗（dialog）只用于风险确认。
- 连续多条通知要用不同 group，否则后一条会顶掉前一条。
- 声音要在投递成功后再播，否则会出现「响了但没收到通知」。
