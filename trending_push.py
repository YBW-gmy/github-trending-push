"""
每两天抓取 GitHub 上 Python/LLM/Agent 相关热门仓库，推送到 QQ。
每个项目附带学习推荐指数。
"""

import json
import os
import re
import smtplib
import sys
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")


def load_config():
    """加载配置：优先环境变量（GitHub Actions），否则读 config.json"""
    env = os.environ

    # GitHub token: 优先 GITHUB_TOKEN（Actions 内置），其次 GH_TOKEN（secret）
    github_token = env.get("GITHUB_TOKEN") or env.get("GH_TOKEN") or ""

    email_sender = env.get("EMAIL_SENDER")
    email_auth = env.get("EMAIL_AUTH_CODE")
    email_receiver = env.get("EMAIL_RECEIVER")
    qmsg_key = env.get("QMSG_KEY")
    qmsg_qq = env.get("QMSG_TARGET_QQ")

    has_env = all([email_sender, email_auth])

    if has_env:
        return {
            "github": {
                "token": github_token,
                "min_stars": 100,
                "lookback_days": 2,
                "max_repos": 10,
            },
            "qq_push": {
                "method": "qmsg",
                "qmsg_key": qmsg_key or "",
                "target_qq": qmsg_qq or "",
            },
            "email_fallback": {
                "enabled": True,
                "smtp_host": "smtp.qq.com",
                "smtp_port": 465,
                "sender": email_sender,
                "auth_code": email_auth,
                "receiver": email_receiver or email_sender,
            },
        }

    # 本地模式：读 config.json
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ── 搜索策略：多个定向查询覆盖 Python + LLM + Agent ──────────────────────

SEARCH_QUERIES = [
    # Python + LLM 开发框架
    "topic:llm topic:python stars:>50",
    "topic:agent topic:python stars:>50",
    # AI Agent 框架
    "topic:ai-agent stars:>100",
    "topic:agent stars:>100 language:python",
    # LLM 应用开发
    "topic:llm topic:agent stars:>100",
    # RAG / 工具链
    "topic:rag stars:>100",
    "topic:langchain stars:>100",
    # MCP / 模型上下文协议
    "topic:mcp stars:>50",
    # 最近创建的 AI 项目
    "ai agent framework stars:>200",
    "llm application stars:>100 language:python",
]

# 用户兴趣关键词，用于相关性打分
INTEREST_KEYWORDS = [
    "python", "llm", "agent", "ai", "gpt", "claude", "openai",
    "langchain", "llamaindex", "rag", "mcp", "tool-use",
    "function-call", "prompt", "chain", "workflow", "autogen",
    "crewai", "semantic-kernel", "copilot", "cursor",
    "embedding", "vector", "chatbot", "assistant", "inference",
    "fine-tune", "lora", "quantize", "ollama", "vllm",
    "transformers", "pytorch", "mlx", "gguf",
]


def fetch_repos_github(cfg):
    """多查询搜索，合并去重"""
    headers = {"Accept": "application/vnd.github+json"}
    token = cfg["github"]["token"]
    if token and token != "your_github_token_here":
        headers["Authorization"] = f"Bearer {token}"

    seen = set()
    all_repos = []

    for query in SEARCH_QUERIES:
        if len(all_repos) >= 30:
            break
        for page in [1, 2]:
            params = {
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": 20,
                "page": page,
            }
            try:
                resp = requests.get(
                    "https://api.github.com/search/repositories",
                    headers=headers,
                    params=params,
                    timeout=20,
                )
                if resp.status_code == 403:
                    print("GitHub API 频率限制，等待中...")
                    time.sleep(10)
                    continue
                if resp.status_code != 200:
                    continue
                items = resp.json().get("items", [])
                for r in items:
                    rid = r["full_name"]
                    if rid not in seen:
                        seen.add(rid)
                        all_repos.append(r)
                time.sleep(1.5)  # 未认证 API 10次/分钟
            except Exception as e:
                print(f"搜索异常: {e}")
                continue

    return all_repos


# ── 学习推荐指数 ──────────────────────────────────────────────────────

def calc_learn_score(repo):
    """
    综合评分 0-100：
    - 热度（0-25）：stars 越高社区越大，找资料越方便
    - 相关性（0-35）：是否匹配 Python/LLM/Agent 方向
    - 文档质量（0-20）：README、Wiki、Website
    - 活跃度（0-10）：最近更新频率
    - 新手友好（0-10）：是否有教程、示例
    """
    score = 0
    stars = repo.get("stargazers_count", 0)
    topics = [t.lower() for t in repo.get("topics", [])]
    language = (repo.get("language") or "").lower()
    desc = (repo.get("description") or "").lower()
    name = repo["full_name"].lower()
    has_wiki = repo.get("has_wiki", False)
    has_pages = repo.get("has_pages", False)
    updated = repo.get("updated_at", "")
    created = repo.get("created_at", "")
    forks = repo.get("forks_count", 0)
    open_issues = repo.get("open_issues_count", 0)

    # ── 热度 25分 ──
    if stars >= 10000:
        score += 25
    elif stars >= 5000:
        score += 22
    elif stars >= 1000:
        score += 18
    elif stars >= 500:
        score += 14
    elif stars >= 100:
        score += 10
    else:
        score += 5

    # ── 相关性 35分 ──
    all_text = f"{name} {desc} {' '.join(topics)} {language}"
    keyword_hits = sum(1 for kw in INTEREST_KEYWORDS if kw in all_text)

    if language == "python":
        score += 10
    elif language in ("typescript", "javascript"):
        score += 4  # JS/TS 生态也有很多 AI 工具

    if keyword_hits >= 8:
        score += 15
    elif keyword_hits >= 5:
        score += 12
    elif keyword_hits >= 3:
        score += 8
    elif keyword_hits >= 1:
        score += 4

    # Agent 专项加分
    is_agent = any(t in all_text for t in ["agent", "multi-agent", "agentic", "autogpt", "crewai", "swarm"])
    is_llm = any(t in all_text for t in ["llm", "large language", "gpt", "claude", "chatgpt", "inference"])

    if is_agent and is_llm:
        score += 10  # LLM + Agent 双重匹配
    elif is_agent:
        score += 7
    elif is_llm:
        score += 5

    score = min(score, 100)  # 不超过 100

    # ── 文档质量 20分 ──
    if repo.get("description") and len(repo["description"]) > 80:
        score += 6  # 详细描述
    elif repo.get("description"):
        score += 3
    if has_wiki:
        score += 5
    if has_pages:
        score += 5
    if forks > 0 and stars > 0:
        # fork/star 比暗示文档和社区质量
        ratio = forks / stars
        if ratio > 0.2:
            score += 4
        elif ratio > 0.1:
            score += 2

    # ── 活跃度 10分 ──
    try:
        updated_dt = datetime.strptime(updated[:10], "%Y-%m-%d")
        days_since_update = (datetime.now() - updated_dt).days
        if days_since_update <= 7:
            score += 10
        elif days_since_update <= 30:
            score += 7
        elif days_since_update <= 90:
            score += 4
        else:
            score += 1
    except Exception:
        score += 3

    # ── 新手友好 10分 ──
    beginner_signals = ["tutorial", "example", "demo", "getting-started", "quickstart", "beginner", "入门", "教程"]
    if any(s in all_text for s in beginner_signals):
        score += 6
    if open_issues > 0:
        # 有 issue 且 star 多说明社区活跃且有人解答
        if stars > 500 and open_issues > 10:
            score += 4
        elif stars > 100:
            score += 2

    return min(score, 100)


def score_to_stars(score):
    """分数转星级"""
    if score >= 85:
        return "⭐⭐⭐⭐⭐"
    elif score >= 70:
        return "⭐⭐⭐⭐"
    elif score >= 55:
        return "⭐⭐⭐"
    elif score >= 40:
        return "⭐⭐"
    else:
        return "⭐"


def score_to_label(score):
    """分数转推荐语"""
    if score >= 85:
        return "强烈推荐，必学"
    elif score >= 70:
        return "非常推荐"
    elif score >= 55:
        return "推荐学习"
    elif score >= 40:
        return "可以关注"
    else:
        return "了解即可"


def summarize_project(repo, desc_cn):
    """概括项目功能（用中文描述做什么的）"""
    desc_lower = (repo.get("description") or "").lower()
    name = repo["full_name"].lower()
    topics = [t.lower() for t in repo.get("topics", [])]
    all_text = f"{name} {desc_lower} {' '.join(topics)}"

    # 按领域分类
    categories = []

    if any(t in all_text for t in ["agent", "multi-agent", "agentic", "swarm", "autogpt", "crewai"]):
        categories.append("AI Agent 框架/平台")
    if any(t in all_text for t in ["rag", "retrieval", "vector", "embedding", "knowledge-base"]):
        categories.append("RAG 检索引擎")
    if any(t in all_text for t in ["mcp", "model-context-protocol"]):
        categories.append("MCP 模型上下文协议工具")
    if any(t in all_text for t in ["langchain", "llamaindex", "langgraph"]):
        categories.append("LLM 应用开发框架")
    if any(t in all_text for t in ["fine-tune", "lora", "qlora", "training"]):
        categories.append("模型训练/微调工具")
    if any(t in all_text for t in ["inference", "vllm", "ollama", "llama.cpp", "tgi"]):
        categories.append("模型推理/部署引擎")
    if any(t in all_text for t in ["prompt", "workflow", "pipeline", "orchestrat"]):
        categories.append("工作流/编排引擎")
    if any(t in all_text for t in ["memory", "context"]):
        categories.append("上下文/记忆管理")
    if any(t in all_text for t in ["tool", "cli", "sdk", "api", "library"]):
        categories.append("开发工具/SDK")
    if any(t in all_text for t in ["chatbot", "assistant", "conversational"]):
        categories.append("对话机器人/助手")
    if any(t in all_text for t in ["benchmark", "eval", "leaderboard"]):
        categories.append("评测/基准测试")
    if any(t in all_text for t in ["tutorial", "course", "learn", "guide", "awesome"]):
        categories.append("学习教程/资源合集")

    category_str = " / ".join(categories[:2]) if categories else "AI 开发工具"

    # 用翻译后的描述作为功能说明
    if desc_cn and desc_cn != "暂无描述" and desc_cn != repo.get("description", ""):
        summary = desc_cn
    else:
        summary = repo.get("description") or "暂无描述"

    return f"[{category_str}] {summary}"


# ── 翻译 ──────────────────────────────────────────────────────────────

def translate_text(text, source="en", target="zh-CN"):
    url = "https://api.mymemory.translated.net/get"
    resp = requests.get(url, params={
        "q": text[:500],
        "langpair": f"{source}|{target}",
    }, timeout=15)
    data = resp.json()
    if data.get("responseStatus") == 200:
        return data["responseData"]["translatedText"]
    return text


def translate_repos(repos):
    cn_descs = []
    for r in repos:
        desc = r.get("description") or ""
        if desc.strip():
            try:
                cn_descs.append(translate_text(desc))
            except Exception:
                cn_descs.append(desc)
        else:
            cn_descs.append("暂无描述")
        time.sleep(0.12)

    all_topics = set()
    for r in repos:
        for t in r.get("topics", []):
            all_topics.add(t)

    topic_cn = {}
    for t in all_topics:
        try:
            topic_cn[t] = translate_text(t)
        except Exception:
            topic_cn[t] = t
        time.sleep(0.08)

    return cn_descs, topic_cn


# ── 邮件/消息生成 ───────────────────────────────────────────────────────

def build_qq_text(cfg, repos, cn_descs, topic_cn, scores):
    date_range = f"{(datetime.now() - timedelta(days=cfg['github']['lookback_days'])).strftime('%m/%d')} - {datetime.now().strftime('%m/%d')}"

    lines = [
        "══════════════════════════",
        "  GitHub 学习推荐速递",
        f"  {date_range} | Python · LLM · Agent",
        f"  共 {len(repos)} 个推荐项目",
        "══════════════════════════",
    ]

    for i, repo in enumerate(repos, 1):
        name = repo["full_name"]
        url = repo["html_url"]
        desc_cn = cn_descs[i - 1]
        stars = repo["stargazers_count"]
        forks = repo.get("forks_count", 0)
        language = repo.get("language") or "N/A"
        s = scores[i - 1]
        stars_icon = score_to_stars(s)
        label = score_to_label(s)
        summary = summarize_project(repo, desc_cn)

        lines.append("")
        lines.append(f"【{i}】{name}")
        lines.append(f"学习指数: {stars_icon} {label} ({s}分)")
        lines.append(f"⭐ {stars}  🍴 {forks}  |  语言: {language}")
        lines.append(f"干什么的: {summary}")
        lines.append(f"链接: {url}")

    lines.append("")
    lines.append("══════════════════════════")
    lines.append(f"下次推送: {(datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')}")
    return "\n".join(lines)


def build_html(cfg, repos, cn_descs, topic_cn, scores):
    rows = []
    for i, repo in enumerate(repos, 1):
        name = repo["full_name"]
        url = repo["html_url"]
        desc_cn = cn_descs[i - 1]
        desc_en = repo.get("description") or ""
        stars = repo["stargazers_count"]
        forks = repo.get("forks_count", 0)
        open_issues = repo.get("open_issues_count", 0)
        language = repo.get("language") or "N/A"
        topics = repo.get("topics", [])
        created = repo.get("created_at", "")[:10]
        s = scores[i - 1]
        stars_icon = score_to_stars(s)
        label = score_to_label(s)
        summary = summarize_project(repo, desc_cn)

        score_color = "#22c55e" if s >= 70 else "#f59e0b" if s >= 55 else "#ef4444"
        score_bg = "#16653433" if s >= 70 else "#78350f33" if s >= 55 else "#7f1d1d33"

        topic_tags = " ".join(
            f'<span style="background:#30363d; padding:2px 8px; border-radius:12px; font-size:12px; margin-right:4px">{topic_cn.get(t, t)}</span>'
            for t in topics[:6]
        )

        rows.append(f"""
        <tr>
            <td style="padding:16px; border-bottom:1px solid #30363d; vertical-align:top">
                <span style="color:#8b949e; font-size:14px">#{i}</span>
            </td>
            <td style="padding:16px; border-bottom:1px solid #30363d; vertical-align:top">
                <div style="display:flex; align-items:center; gap:12px; margin-bottom:6px">
                    <a href="{url}" style="color:#58a6ff; font-size:18px; font-weight:600; text-decoration:none" target="_blank">{name}</a>
                    <span style="background:{score_bg}; color:{score_color}; padding:4px 12px; border-radius:16px; font-size:13px; font-weight:600; white-space:nowrap">
                        {stars_icon} {label} {s}分
                    </span>
                </div>
                <div style="background:#1f6feb0a; border-left:3px solid #58a6ff; padding:8px 12px; margin:8px 0; border-radius:4px; color:#c9d1d9; line-height:1.6">
                    <strong style="color:#58a6ff">干什么的：</strong>{summary}
                </div>
                <div style="color:#6e7681; font-size:12px; margin-bottom:8px">{desc_en}</div>
                <div style="margin-bottom:6px">
                    <span style="background:#1f6feb33; color:#58a6ff; padding:2px 8px; border-radius:12px; font-size:12px; margin-right:6px">{language}</span>
                    {topic_tags}
                </div>
                <div style="color:#8b949e; font-size:13px; margin-bottom:8px">
                    创建: {created} &nbsp;|&nbsp; ⭐{stars} &nbsp; 🍴{forks} &nbsp; 📋{open_issues} issues
                </div>
            </td>
        </tr>""")

    date_start = (datetime.now() - timedelta(days=cfg["github"]["lookback_days"])).strftime("%m/%d")
    date_end = datetime.now().strftime("%m/%d")
    next_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")

    return """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="background:#0d1117; margin:0; padding:0; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:750px; margin:0 auto">
    <tr>
        <td style="padding:24px 20px; text-align:center; background:#161b22; border-bottom:1px solid #30363d">
            <h1 style="color:#f0f6fc; margin:0; font-size:22px">GitHub 学习推荐速递</h1>
            <p style="color:#8b949e; margin:6px 0 0; font-size:13px">
                {date_start} - {date_end} &nbsp;|&nbsp; Python · LLM · Agent &nbsp;|&nbsp; 每两天推送
            </p>
        </td>
    </tr>
    <tr>
        <td style="background:#0d1117; padding:12px 20px">
            <table width="100%" cellpadding="0" cellspacing="0">{rows}</table>
        </td>
    </tr>
    <tr>
        <td style="padding:20px; text-align:center; color:#6e7681; font-size:12px; background:#161b22; border-top:1px solid #30363d">
            由 GitHub Learning Push 自动生成 &nbsp;|&nbsp; 下次推送约在 {next_date}
        </td>
    </tr>
</table>
</body>
</html>""".format(date_start=date_start, date_end=date_end, rows="".join(rows), next_date=next_date)


# ── 推送 ──────────────────────────────────────────────────────────────

def push_qq_qmsg(cfg, text):
    key = cfg["qq_push"]["qmsg_key"]
    target_qq = cfg["qq_push"]["target_qq"]
    url = f"https://qmsg.zendee.cn/send/{key}"
    text = text[:14000]

    resp = requests.post(url, data={"qq": target_qq, "msg": text}, timeout=15)
    resp.encoding = "utf-8"
    try:
        data = resp.json()
        if data.get("success"):
            print(f"QQ推送成功: {data.get('reason', 'OK')}")
            return data
        else:
            print(f"QQ推送失败: {data.get('reason', 'unknown')}", file=sys.stderr)
            return None
    except Exception:
        print(f"Qmsg 响应异常: {resp.text[:200]}", file=sys.stderr)
        return None


def send_email(cfg, repos, cn_descs, topic_cn, scores):
    ec = cfg["email_fallback"]
    if not ec.get("enabled"):
        return False
    if ec["sender"] == "your_qq_email@qq.com":
        print("邮件未配置，跳过。")
        return False

    send_from = ec["sender"]
    send_to = ec.get("receiver") or send_from

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "GitHub 学习推荐 | {} - Python/LLM/Agent {}个项目".format(
        datetime.now().strftime("%m/%d"), len(repos)
    )
    msg["From"] = send_from
    msg["To"] = send_to

    msg.attach(MIMEText(build_qq_text(cfg, repos, cn_descs, topic_cn, scores), "plain", "utf-8"))
    msg.attach(MIMEText(build_html(cfg, repos, cn_descs, topic_cn, scores), "html", "utf-8"))

    with smtplib.SMTP_SSL(ec["smtp_host"], ec["smtp_port"], timeout=15) as smtp:
        smtp.login(send_from, ec["auth_code"])
        smtp.sendmail(send_from, [send_to], msg.as_string())
    print("邮件已发送到 {}".format(send_to))
    return True


# ── 主流程 ────────────────────────────────────────────────────────────

def main():
    cfg = load_config()

    print("正在搜索 GitHub (Python/LLM/Agent)...")
    repos = fetch_repos_github(cfg)
    if not repos:
        print("没有找到相关仓库。")
        return

    # 打分 + 排序
    print("正在计算学习推荐指数...")
    scored = [(calc_learn_score(r), r) for r in repos]
    scored.sort(key=lambda x: x[0], reverse=True)

    max_repos = cfg["github"]["max_repos"]
    top = scored[:max_repos]
    scores = [s for s, _ in top]
    repos = [r for _, r in top]

    print(f"得分最高 {len(repos)} 个项目:")

    # 翻译
    print("正在翻译描述...")
    cn_descs, topic_cn = translate_repos(repos)

    # 打印预览（过滤 emoji 等特殊字符）
    for i, (r, s) in enumerate(zip(repos, scores), 1):
        esc_stars = score_to_stars(s).replace("⭐", "*").replace("★", "*")
        name = r['full_name'].encode("ascii", errors="replace").decode("ascii")
        desc = (r.get("description") or "")[:60].encode("ascii", errors="replace").decode("ascii")
        print(f"  {i}. [{esc_stars} {s}分] {name} stars={r['stargazers_count']} - {desc}")

    # 推送
    text = build_qq_text(cfg, repos, cn_descs, topic_cn, scores)
    result = push_qq_qmsg(cfg, text)
    if result is None:
        print("Qmsg 推送失败，尝试邮件...")
        ok = send_email(cfg, repos, cn_descs, topic_cn, scores)
        if not ok:
            print("所有推送通道均失败。")
    else:
        send_email(cfg, repos, cn_descs, topic_cn, scores)

    print("推送完成！")


if __name__ == "__main__":
    main()
