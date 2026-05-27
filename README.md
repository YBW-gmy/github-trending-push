# GitHub 学习推荐速递

每两天自动抓取 GitHub 上 **Python / LLM / AI Agent** 方向热门仓库，翻译成中文并附带学习推荐指数，推送到 QQ 邮箱。

## 效果

<img src="https://img.shields.io/badge/%E6%8E%A8%E9%80%81%E9%A2%91%E7%8E%87-%E6%AF%8F2%E5%A4%A9-blue" />

每封邮件长这样：

```
【1】langchain-ai/langgraph  ⭐33104  🍴...
学习指数: ⭐⭐⭐⭐ 推荐学习 (84分)
干什么的: [LLM 应用开发框架 / 工作流编排引擎] 构建弹性 AI Agent 的图编排框架
链接: https://github.com/langchain-ai/langgraph
```

- **干什么的**：一句话概括项目功能
- **学习指数**：综合热度、相关性、文档质量、活跃度打分（0-100）

## 原理

```
GitHub Actions 定时触发 → 搜索 GitHub API → 打分排序 → MyMemory 翻译 → QQ 邮箱
```

不需要自己的服务器，不需要电脑开机，全跑在 GitHub 免费云上。

## 本地运行

```bash
pip install -r requirements.txt
cp config.example.json config.json   # 编辑填入邮箱授权码
python trending_push.py
```

## 配置项

| 环境变量 | 说明 |
|---------|------|
| `EMAIL_SENDER` | QQ 邮箱地址 |
| `EMAIL_AUTH_CODE` | QQ 邮箱 SMTP 授权码 |
| `GITHUB_TOKEN` | GitHub Token（可选，提高 API 频率） |
