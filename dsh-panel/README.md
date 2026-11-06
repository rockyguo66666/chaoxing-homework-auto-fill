# 学习通自动化 · DSH 左侧作业看板

这是「学习通作业自动化」项目的界面更新：把每天推送的作业清单从对话里搬出来，
在 DeepSeek Harness 左侧「自动化任务」下方单独开一个 **「学习通自动化」** 入口，
点开是一页可交互的作业卡片看板。

## 卡片内容

- 课程名、作业名
- **是否已提交**：`未交` → 「未提交」，`待批阅` → 「已提交 · 待批阅」（其余状态归为已提交）
- **截止日期**：直接显示 `deadline`；`semester_end` 显示「截止：学期末」；
  过期且关闭显示「已截止 · 不可作答」；无数据显示「截止未知」
- 剩余时间（扫描结果里的 `remainText`）
- **点击整张卡片** = 新标签打开该作业的学习通页面（`taskUrl` 直达链接）

页面还提供：全部 / 未交 / 已交筛选、课程或作业名搜索、手动刷新；
每 60 秒自动重读一次本机扫描结果，顶部显示扫描时间、统计与超过 26 小时的过期提示。

## 数据来源

只读 `scan.js` 产出的 `result.json`（结构：`checkedAt / semesterEnd / courses[].items[]`），
按以下顺序取存在且最新的一份：

1. 插件行 `config.resultPath`（在 `cordis.patch.yml` 里配置）
2. 环境变量 `CX_RESULT`
3. `~/.chaoxing-homework/result.json`（本技能默认）
4. `~/.openclaw/workspace/tools/chaoxing/result.json`

Host 插件注册 `GET /api/chaoxing.homework`，Client 通过同源 fetch 取数据；
不写入、不上传任何作业数据，也不需要学习通登录态（登录态只在 `scan.js` 那侧）。

## 安装

需要一个 DeepSeek Harness 的 Web profile。推荐用插件管理器：

```bash
# 在本仓库根目录
/…/dsh 的插件管理器：install_bundle，target 指向本目录的绝对路径
# 例如：plugin_manager install_bundle /path/to/chaoxing-homework-auto-fill/dsh-panel/chaoxing-homework-panel
```

或者在 profile 里手工挂载（等效做法，HMR 会监听 `package.json` 自动生效）：

```bash
ln -s /abs/path/dsh-panel/chaoxing-homework-panel \
  ~/.dsh/profiles/web/node_modules/@local/chaoxing-homework-panel
# 再在 ~/.dsh/profiles/web/package.json 里：
#   dependencies["@local/chaoxing-homework-panel"] = "link:/abs/path/dsh-panel/chaoxing-homework-panel"
#   dsh.profile.bundles 追加 "@local/chaoxing-homework-panel"
```

安装后左侧「自动化任务」下方出现「学习通自动化」；若没出现，刷新一次页面即可。
插件是纯前端展示：遵循项目铁律，**默认永远不点「提交」**，写作业仍走 `scripts/` 那套流程，
提交按钮始终由本人点。

## 实现要点

- `index.js`：Host 插件，`ctx.connection.fetch.register` 注册 API 路由，实时读 JSON 并归一化字段
- `client.js`：Client 插件，`sidebar.panellist` 注册 order 11 的入口（`schedules` 为 10），
  `main` 注册同 key 的 React 页面；只用 `--dsw-alias-*` 主题 token，不 import Harness Client 包
- `locale/*.json`：中英文案；`icon.svg`：插件图标
- 亮/暗主题跟随宿主；组件卸载时自动清理定时器与样式
