# 学习通作业自动化（技能文件夹）

这个**文件夹本身就是一个智能体技能**。把它交给 DeepSeek Harness（或任何支持
`SKILL.md` 的智能体框架），说一句「安装这个文件夹的技能」，就能获得一整套
「查未交 → 抓题 → 作答 → 暂存 → 提醒」的协作流程：

- 自动分流题型（选择直填 / 物理数学出手写图 / 长解答直接打字）
- 配套模拟笔迹：采样本人手写照片生成个人字库，再渲染成答题纸图片
- 默认**只「暂时保存」绝不提交**，提交需用户明确要求并确认
- 每天自动推送未交清单（含距截止天数），不重复打扰

> 仓库地址：https://github.com/rockyguo66666/chaoxing-homework-auto-fill  
> GitHub 仓库名不接受中文，中文名放在仓库简介与标题里。

## 一句话安装

```bash
bash scripts/setup.sh            # 依赖（自动装 playwright + 浏览器 + Python 渲染依赖）
bash scripts/install-skill.sh    # 装成 DSH / Claude Code 技能（同名旧版自动备份）
node scripts/relogin.js         # 扫码登录学习通
```

装完直接跟智能体说：

> 查一下我有哪些学习通作业没交

或者：

> 把「大学物理 光的干涉」这份作业做了

## 文件夹里有什么

```
SKILL.md                      智能体读这个：铁律、分流规则、流程、交互规范、踩坑速查
scripts/                      扫描/抓题/填答/插图/混合卷/推送/提交/出图/安装/自检
lib/                          路径与浏览器、通知的公共层
skills/handwriting-homework/  模拟笔迹：采样照片 → 生成个人字库 → 渲染答题纸
references/                   踩坑清单与题型分流细则
examples/launchd.plist        macOS 定时推送示例
```

---

## 答案文件格式（手写答题纸）

`cx sheet` 读的答案文件**第一行必须以「答：」开头**，否则会被当成题干而不出字。
之后按你想要的排版写：**一行一步、段落之间空一行**；渲染器会原样保留换行，不再把步骤挤成一段。
每行建议 ≤30 字符（超过会被折断）；超一页就拆成两个文件分别渲染。

```
答：解：设…
第一步，写清条件。
第二步，列出方程。

所以结论是…。
```

## 特点

- **零人工搬运**：抓题直接产出每题高清图 + `questions.json`，填答脚本按题号写回对应答题框。
- **答案分型处理**：选择题点选、简答/计算题可打字也可插手写答题纸图片。
- **写完自证**：暂存后关掉浏览器重开，逐题读回选中项/图片，确认真的落服务端。
- **登录态自持**：cookie 与浏览器 profile 都在你自己的目录里，脚本只读自己的会话。
- **路径全部参数化**：不依赖任何特定用户的家目录。

## 安装（只需要一次 npm install）

```bash
git clone <仓库地址> cx-chaoxing-homework
cd cx-chaoxing-homework
npm install            # 会自动装 playwright 并下载浏览器
```

**不用再装别的东西**：

- 浏览器：`npm install` 的 postinstall 会自动下载 Playwright 自带的 Chromium；
  想用系统里已有的 Chrome/Edge，设 `CX_CHANNEL=chrome` 或 `CX_CHANNEL=msedge` 即可。
- 手写答题纸渲染所需的 Python 依赖（numpy / Pillow / fontTools）：
  `cx sheet` **首次运行自动建 venv 并安装**，之后直接用；
  若你的系统 python 已经带这些库，会直接复用，连 venv 都不建。
- 想模拟本人笔迹（采样照片 → 生成个人字库）：`skills/handwriting-homework/` 里已包含全套脚本与说明。

> 需要 Python 3.8+（系统自带即可）。完全不想装 Python 时，
> 选择题/打字作答这条路不需要 Python，照常可用。

## 快速开始

```bash
cx login                          # 1. 扫码登录（浏览器会弹出）
cx scan                           # 2. 扫描全部课程的未交作业
cx list                           # 3. 看清单（含距截止天数）

cx grab 高等数学 第三章作业        # 4. 抓题：每题出图 + questions.json
#   然后按题型写 answers.json / choices.json
cx mixed 高等数学 第三章作业 choices.json images.json   # 5. 填答并暂存
cx push --force                   # 6. 推送待办提醒
cx sheet 第1题.txt --out 答题纸.png --preset 娃娃体   # 6. 出手写答题纸图
cx push --force                   # 7. 推送待办提醒
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

## 给 AI Agent 用：装成智能体技能

本包自带全部脚本与配套的模拟笔迹能力，**装上就能用，不需要再装别的技能**。

```bash
# 一键装成技能：DeepSeek Harness 与 Claude Code 都会自动认到
bash scripts/install-skill.sh

# 或装到指定位置（任何支持 SKILL.md 的框架都行）
bash scripts/install-skill.sh ~/.dsh/skills/chaoxing-homework
```

装好后：

- 智能体侧：框架读取技能目录里的 `SKILL.md` 即可（DeepSeek Harness 的 `~/.dsh/skills/`、
  Claude Code 的 `~/.claude/skills/` 都在安装脚本的默认目标里）。
- 命令行侧：在仓库里执行 `npm link` 就能直接用 `cx` 命令；
  不 link 也可以 `node bin/cx.js <命令>`，或在技能目录里 `node scripts/*.js`。

技能包里包含：

```
SKILL.md                     题型分流 + 标准流程 + 踩坑清单（智能体读这个）
scripts/                     扫描/抓题/填答/插图/混合卷/推送/提交/渲染
lib/                         路径与浏览器、通知的公共层
references/                  踩坑与分流细则
skills/handwriting-homework/ 模拟笔迹：采样照片→生成个人字库→渲染答题纸
```

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