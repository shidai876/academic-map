# Academic Map 2.0 免费科研雷达版

这是一个**不使用付费 GPT API**的个人博士科研雷达，面向膜分离 / 纳滤 / 二维层状膜 / COF / 离子筛分等方向。

## 它每天自动做什么

每天约 **06:17（UTC+8）**：
1. 从 OpenAlex + Crossref 搜索最近 3 天的新论文（3 天窗口用于容忍数据库收录延迟）。
2. 去重。
3. 按你关心的主题与关键词自动打分。
4. 提取题名、期刊、日期、作者、机构、摘要、关键词和数据线索。
5. 更新“本周热点、活跃作者、活跃团队、活跃期刊”。
6. 自动重新发布 GitHub Pages。

**没有调用付费 AI。**“自动结构化速览”只基于公开元数据和摘要做规则提取，避免把机器生成内容冒充论文原意。

---

# 最简单部署：6 步

## 1. 注册 / 登录 GitHub
https://github.com

## 2. 新建一个 Public（公开）仓库
建议仓库名：
`academic-map`

> GitHub Free 的 Pages 可用于 public repository。  
> 不要把未发表实验、私人笔记、导师信息放进仓库。

## 3. 把本压缩包解压后的**所有文件和文件夹**上传到仓库根目录
上传后应看到：

```text
.github/workflows/daily-radar.yml
data/history.json
scripts/update_radar.py
site/index.html
site/data/radar.json
config.json
README.md
```

注意 `.github` 是隐藏风格的文件夹，但 GitHub 网页里能正常看到。

## 4. 开启 GitHub Pages
进入仓库：

`Settings → Pages → Build and deployment → Source → GitHub Actions`

## 5. 手动跑第一次
进入：

`Actions → Daily Research Radar → Run workflow → Run workflow`

等几分钟。第一次成功后：

`Settings → Pages`

会出现你的固定网址，通常类似：

`https://你的GitHub用户名.github.io/academic-map/`

以后收藏这个网址即可。

## 6. 建议但不是强制：添加免费 OpenAlex API Key
OpenAlex 当前提供免费 API key / 免费每日额度。获取后：

GitHub 仓库 → `Settings → Secrets and variables → Actions → Secrets → New repository secret`

名称：
`OPENALEX_API_KEY`

值：
你的免费 key

Crossref 无需注册即可使用；如愿意，可在 `Variables` 新建：

`CROSSREF_MAILTO = 你的邮箱`

这只是用于 Crossref polite pool，不会显示在网页里。

---

# 你的私人数据会不会公开？

不会自动公开。

公开仓库中只有：
- 网站程序
- 检索配置
- 公开论文元数据
- 自动生成的趋势历史

以下内容保存在你浏览器 localStorage：
- 人物库里的个人笔记
- 团队库里的个人笔记
- 期刊库
- 热点库
- 收藏文献
- 待补课

因此：
- 换电脑 / 换浏览器之前请在网页“备份”中导出 JSON。
- 清理浏览器网站数据前也要先备份。
- 从旧版 Academic Map 1.0 导出的 JSON 可以直接尝试导入 2.0。

---

# 如何调整“什么论文最值得我看”

编辑根目录 `config.json`。

你可以直接修改：

### `queries`
每天搜索的关键词。

### `topic_rules`
自动归类成：
- 二维层状膜
- 离子筛分
- COF/MOF膜
- 纳滤
- 有机溶剂纳滤
- 聚酰胺/TFC
- 纳米通道/限域传输
- 硫属二维材料
- 脱盐/水处理

### `weighted_keywords`
与个人课题匹配的权重。

### `journal_boost`
你认可的重点期刊额外加分。

修改后可到 Actions 手动点一次 Run workflow 立即刷新。

---

# 网站中“复制给 GPT 分析”

每篇论文都有“复制给 GPT 分析”。

它会把：
- 标题
- 期刊
- DOI
- 作者
- 机构
- 摘要

连同一个结构化分析问题复制到剪贴板。

然后你直接粘贴到 ChatGPT 即可。这样只对真正值得精读的 2–3 篇使用 GPT，而不是每天后台付费调用 API。

---

# 关于“通讯作者”

OpenAlex / Crossref 的公共元数据并不总是可靠提供通讯作者标记，因此本版**不会靠作者排序猜通讯作者**。

这比错误地把末位作者自动标成“通讯作者”更适合科研使用。后续如果来源明确提供通讯作者字段，再单独显示。

---

# 维护提醒

GitHub 文档说明：public repository 的 scheduled workflow 在 **60 天没有 repository activity** 时可能被自动禁用。

本项目每天会更新 `site/data/last_run.txt` 并产生自动提交，正常情况下仓库持续有活动；如果很久没更新，可进入 `Actions → Daily Research Radar` 手动重新启用 / Run workflow。

---

# 数据源

- OpenAlex：公开学术知识图谱。
- Crossref：公开 DOI / 出版元数据 REST API。

该网站是个人科研情报辅助工具。正式引用、论文结论、作者身份和性能数据仍应以出版社论文原文为准。
