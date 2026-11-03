---
name: chaoxing-homework
description: >-
  学习通(超星)作业自动化：扫描未交作业清单、推送待办提醒、抓取题目、按题型分流作答
  （选择题点选 / 解答与计算题打字或出手写答题纸图片）、上传后只「暂时保存」不提交。
  当用户提到 学习通、超星、作业待办、未交作业、手写作业上交、作业推送 时使用。
metadata:
  dsh:
    requiresBins: [node]
---

# 学习通作业助手

**铁律：本技能默认只做「暂时保存」，绝不点「提交」**。提交是不可逆操作，
必须由用户本人完成，或由用户明确要求并显式确认后由脚本执行 `cx submit … --yes`。

## 分流规则（做题前先判题型）

| 情况 | 做法 | 命令 |
|---|---|---|
| 全卷纯选择/判断 | 点选填入 | `cx mixed …`（images 传 `{}`） |
| 选择 + 判断 + 解答混合 | 一趟：点选 + 计算题插图 | `cx mixed <课程> <作业> choices.json images.json` |
| 解答/计算，且物理或数学类 | **无条件**手写答题纸图片（不看字数） | `cx img …` |
| 解答/填空，步骤 ≤1000 字 | 手写答题纸图片 | `cx img …` |
| 解答/填空，步骤 >1000 字 | 直接打字 | `cx fill <课程> <作业> answers.json` |
| 交程序/软件作品类 | **不做**，只在提醒里提示 | — |

「步骤字数」= 准备写进答题框的答案正文字符数。

## 如何使用本技能

本技能自带全部脚本，**不需要另外安装任何技能或工具**。

```bash
# 安装成智能体技能（DeepSeek Harness / Claude Code 等通用）
bash scripts/install-skill.sh              # 装到 ~/.dsh/skills 与 ~/.claude/skills
bash scripts/install-skill.sh <目标目录>    # 或装到指定位置

# 装好后命令有两种写法，效果相同：
node scripts/scan.js          # 直接用脚本
cx scan                       # 若执行过 npm link
```

配套的**模拟笔迹**能力已打包在 `skills/handwriting-homework/`：
采样照片 → 生成个人字库 → 渲染答题纸，全套脚本与说明都在里面，
首次运行会自动准备 Python 依赖（numpy / Pillow / fontTools）。


作为技能安装后，技能目录里就有完整的 `scripts/`；智能体可直接调用：

```bash
node <技能目录>/scripts/scan.js
node <技能目录>/scripts/mixed-work.js <课程> <作业> choices.json images.json
node <技能目录>/scripts/sheet.js 答案.txt --out 图.png --preset 娃娃体
```
## 标准流程

```
1 扫描 → cx scan                       (约几分钟，产出 result.json)
2 看清单 → cx list                      (未交项 + 距截止天数)
3 抓题   → cx grab <课程> <作业> <目录> (每题 q1.png… + questions.json)
4 读题   → 优先 read_image 读截图；有疑就换模型交叉读，别猜
5 写答案 → 完整写「解:…(1)…(2)…」带每步依据；判型定分流
6 出图   → 手写答题纸渲染；渲染完必须亲眼看图
7 写入   → cx mixed / cx fill / cx img  (内部自动「暂时保存」)
8 验证   → 关掉浏览器重开答题页，逐题读回选中项与图片，确认落服务端
9 汇报   → 课程+作业+做了什么+验证结果+「等你提交」；横幅提醒收尾
```

## 每日提醒

- 数据源：`$CX_HOME/result.json`（默认 `~/.chaoxing-homework/result.json`）。
- 扫描：`cx scan`（约 5 分钟，跑完自动写 result.json）。
- 推送：`cx push --force`（读 result.json → 横幅通知）。
- **新鲜度闸**：result.json 超过 26 小时视为过期，先重扫再推。
- **幂等闸**：同一份扫描 12 小时内只推一次，避免主任务与兜底任务重复打扰。
- 定时示例见 `examples/launchd.plist`。

## 答案文件格式

- 文字：`{"1": "解：…", "2": "…"}`，键是题号（从 1 开始）。
- 选择：`{"1": "D", "2": "~对"}` —— 字母按选项**显示顺序**；判断题用 `~对`/`~错` 按文字匹配。
- 插图：`{"6": "/abs/path.png"}`，题号 → 图片路径。

## 关键坑（实测踩过）

1. **profile 单实例锁**：脚本异常退出可能锁死后续 →
   `pkill -f "user-data-dir=.*profile"; rm -f $CX_PROFILE/SingletonLock`。
2. **NEED_RELOGIN**：登录态失效 → 让用户在 `cx login` 扫码，不要碰账号密码。
3. **课程匹配**：先去书名号，全等优先、包含兜底（课名常带「2026秋季 」前缀）。
4. **「暂时保存」是真落服务端**：重开仍在；别把「保存后页面没跳转」当失败。
5. **图走上传接口**：页内 fetch UEditor `imageUrl` 上传拿 ananas URL 再 setContent；
   直连下载会被防盗链挡。
6. **答题页是 goTask 开的新标签**：轮询 `ctx.pages()` 找 /dowork/，最多等 ~30s；
   等不够会拿到课程页（题目数 0），要能识别并中止而不是误写。
7. **UEditor 实例号 ≠ 题号**：一份卷可能只有 2 个编辑器却有 7 题。
   插图前按题目 DOM 里 `iframe[id^="ueditor_"]` 的下标定位。
8. **重开验证只看答题区**：题干本身也含 `<img>`（矩阵图），
   必须读编辑器内容判定，别拿整题 innerHTML。
9. **选择题按显示顺序，别按 data 属性**：平台会打乱显示序而 data 字母不变。
10. **题干常是手机拍的纸面照片**：取 CDN 原图（`data-original` 里的 `/star3/origin/`）
    比页面截图清晰得多；矩阵图是懒加载，要 `scrollIntoView` + 等 `onload`。
11. **数值题别手算**：用 sympy 之类精确复核后再写。
12. **看不清就问，别猜**：题干有歧义时先问用户。

更细的专题见 `references/`。

## 边界

- 只操作用户本人账号的作业。
- 默认永远不点「提交」；写操作后必须重开验证。
- 待办提醒只用横幅通知，弹窗仅用于风险确认或需要用户选择时。