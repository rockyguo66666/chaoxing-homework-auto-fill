# 学习通作业自动化（cx）

把「查未交作业 → 抓题 → 填答 → 暂存 → 提醒」整条流程做成一套可复用的脚本。
既可以当 **AI Agent 技能**（见 [SKILL.md](SKILL.md)），也可以当 **独立命令行工具**（见下）。

> ⚠️ **默认只做「暂时保存」，永远不自动点「提交」**。
> 提交是不可逆操作，必须显式 `cx submit ... --yes`。
> 使用者需自行确保符合所在学校/课程的规定与学术诚信要求。

---

## 特点

- **零人工搬运**：抓题直接产出每题高清图 + `questions.json`，填答脚本按题号写回对应答题框。
- **答案分型处理**：选择题点选、简答/计算题可打字也可插手写答题纸图片。
- **写完自证**：暂存后关掉浏览器重开，逐题读回选中项/图片，确认真的落服务端。
- **登录态自持**：cookie 与浏览器 profile 都在你自己的目录里，脚本只读自己的会话。
- **路径全部参数化**：不依赖任何特定用户的家目录。

## 安装

```bash
git clone <你的仓库地址> cx-chaoxing-homework
cd cx-chaoxing-homework
npm install            # 会装 playwright
npx playwright install chromium   # 若用自带 chromium
```

浏览器可选：默认 `msedge`（Edge）。用 Chrome 改 `CX_CHANNEL=chrome`，
用 Playwright 自带的 Chromium 改 `CX_CHANNEL=bundled`。

## 快速开始

```bash
cx login                          # 1. 扫码登录（浏览器会弹出）
cx scan                           # 2. 扫描全部课程的未交作业
cx list                           # 3. 看清单（含距截止天数）

cx grab 高等数学 第三章作业        # 4. 抓题：每题出图 + questions.json
#   然后按题型写 answers.json / choices.json
cx mixed 高等数学 第三章作业 choices.json images.json   # 5. 填答并暂存
cx push --force                   # 6. 推送待办提醒
```

所有配置通过环境变量，默认落在 `~/.chaoxing-homework`：

| 变量 | 含义 | 默认 |
|---|---|---|
| `CX_HOME` | 数据根目录 | `~/.chaoxing-homework` |
| `CX_PROFILE` | 浏览器用户目录 | `$CX_HOME/profile` |
| `CX_COOKIES` | cookie 文件 | `$CX_HOME/cookies.json` |
| `CX_RESULT` | 扫描结果 | `$CX_HOME/result.json` |
| `CX_IGNORE` | 忽略清单 | `$CX_HOME/ignore-list.json` |
| `CX_OUT` | 产物目录 | `$CX_HOME/runs` |
| `CX_CHANNEL` | `msedge`/`chrome`/`bundled` | `msedge` |
| `CX_HEADLESS` | `0` 为有头模式 | `1` |
| `CX_NOTIFY_CMD` | 自定义通知命令 | 无（macOS 走 osascript） |

## 命令一览

| 命令 | 作用 |
|---|---|
| `cx login` | 扫码登录并导出 cookie |
| `cx scan` | 扫描所有课程未交作业，写 `result.json` |
| `cx list` | 打印未交清单 |
| `cx grab <课程> <作业> [目录]` | 抓题：每题高清图 + `questions.json` |
| `cx fill <课程> <作业> <answers.json>` | 文字答案 → 暂时保存 |
| `cx img <课程> <作业> <题号> <png>` | 手写答题纸图片 → 暂时保存 |
| `cx mixed <课程> <作业> <choices.json> <images.json>` | 混合卷一趟做完 |
| `cx push [--force] [--dry]` | 推送待办提醒（横幅） |
| `cx submit <课程> <作业> --yes` | **提交**（不可逆，需 `--yes`） |
| `node scripts/choice-fill.js … --submit --yes` | 选择题作答并提交（同样需 `--yes`） |

### 答案文件格式

文字答案（`answers.json`），键是题号（从 1 开始）：

```json
{ "1": "解：设电流为 I，由 KCL 得 …", "2": "…" }
```

选择题 + 插图混合卷（`choices.json` + `images.json`）：

```json
// choices.json —— 字母按选项「显示顺序」，判断题用 "~对"/"~错" 按文字匹配
{ "1": "D", "2": "B", "3": "~对" }
```

```json
// images.json —— 题号 → 手写答题纸图片路径
{ "6": "/abs/path/答题纸-第6题.png" }
```

## 给 AI Agent 用：技能形态

把本目录当作 skill 安装（Claude Code / DSH 等都吃 `SKILL.md`）：

- `SKILL.md` —— 题型分流规则、标准流程、实测踩坑清单
- `scripts/` —— 上面的全部脚本
- `references/` —— 更细的专题文档

分流规则（决定一道解答题该打字还是出图）：

| 情况 | 做法 |
|---|---|
| 选择/判断 | 直接点选填入 |
| 物理 / 数学类解答计算题 | 一律出手写答题纸图片 |
| 其他解答填空题，步骤 ≤1000 字 | 手写答题纸图片 |
| 其他解答填空题，步骤 >1000 字 | 直接打字 |

手写答题纸图片可以用任意渲染管线生成（本仓库不绑定特定字体），
也可以配合 `handwriting-homework` 这类技能做「本人字迹」渲染。

## 定时提醒

见 [examples/launchd.plist](examples/launchd.plist)：

```bash
cp examples/launchd.plist ~/Library/LaunchAgents/cx-push.plist
launchctl load ~/Library/LaunchAgents/cx-push.plist
```

脚本自带幂等闸：同一份扫描结果 12 小时内只推一次，避免主任务与兜底任务重复打扰。

## 目录结构

```
bin/cx.js              统一 CLI 入口
lib/config.js          所有路径与开关（唯一真源）
lib/browser.js         带登录态开浏览器 + 导航到答题页
lib/notify.js          跨平台通知
lib/playwright.js      playwright 解析（本地优先，回退全局）
scripts/scan.js        扫描未交作业 → result.json
scripts/summarize.js   result.json → 人类可读清单
scripts/relogin.js     扫码登录，导出 cookie
scripts/grab-qs.js     抓题：每题截图 + questions.json
scripts/choice-fill.js 选择题/判断题/连线题点选
scripts/fill-save.js   文字答案填入
scripts/insert-img.js  手写答题纸插图
scripts/mixed-work.js  混合卷一趟（点选 + 插图 + 重开验证）
scripts/push.js        待办推送
scripts/submit.js      提交（需 --yes）
references/            踩坑与专题文档
```

## 安全设计

- 所有作答脚本**默认只点「暂时保存」**，不碰「提交」。
- 提交是唯一不可逆操作，两条路径都需要显式 `--yes`：
  `cx submit … --yes` 与 `choice-fill.js … --submit --yes`。
  只给 `--submit` 不给 `--yes` 时，脚本会照常保存，并明确提示「跳过提交」。
- 写操作后脚本会**关掉浏览器重开**读回，确认真的落服务端。

## 隐私

仓库**不包含**任何登录态或个人信息。以下内容已在 `.gitignore` 中排除：

```
cookies.json     登录 cookie（= 你的账号，别提交）
profile/         浏览器用户目录（几百 MB）
result.json      扫描结果（含课程名、作业名、截止时间）
ignore-list.json 你的忽略清单
qr.png           登录二维码
```

`ignore-list.json` 用现成的 [ignore-list.example.json](ignore-list.example.json) 复制一份即可。

## 常见问题

**`NEED_RELOGIN`** —— 登录态失效，跑 `cx login` 重新扫码。

**抓出来的题看不清** —— 题干常是手机拍的纸面照片，
取 CDN 原图（`data-original` 的 `/star3/origin/` 地址）比页面截图清晰得多。

**插图插到了错误的题** —— UEditor 实例号 ≠ 题号，一份卷可能只有 2 个编辑器却有 7 题；
必须按题目 DOM 里 `iframe[id^="ueditor_"]` 的下标定位。

更多踩坑见 [references/pitfalls.md](references/pitfalls.md)。

## License

MIT