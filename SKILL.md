---
name: solvea-social-monitor
description: "Solvea 社媒 Agent 运营监控中枢。安装后自动注册到 GTM 网络，每天早晚向钉钉群汇报含帖子链接的运营日报，支持通过钉钉 @AgentName 下发 Taste/Prompt 优化反馈。Triggers: social monitor, agent monitor, gtm monitor, solvea monitor, taste review, 社媒监控, agent状态"
allowed-tools: Bash
metadata:
  openclaw:
    homepage: https://github.com/mguozhen/solvea-agent-bus
---

# Solvea Social Monitor

多机器社媒 Agent 运营监控中枢，接入 Solvea GTM 钉钉群。

## 安装（每台机器执行一次）

**Mac / Linux：**
```bash
curl -sSL https://raw.githubusercontent.com/mguozhen/solvea-agent-bus/main/scripts/bootstrap.sh | bash
```

**Windows（Git Bash）：**
```bash
curl -sSL https://raw.githubusercontent.com/mguozhen/solvea-agent-bus/main/scripts/bootstrap.sh | bash
```

安装时只需填写：
- **Agent 名称**（如 `reddit-hunter` / `x-poster`）
- **负责平台**（如 `reddit x` / `linkedin`）
- **机器位置**（如 `mac-mini-hangzhou` / `windows-la`）
- **负责人**（如 `Boyuan` / `Ivy`）
- **平台账号**（X/Reddit/LinkedIn，可留空）

所有认证（GitHub Token、钉钉 Webhook/AppKey/AppSecret）已内置，**安装完成后 3 分钟内出现在钉钉晨报。**

## 钉钉指令

```
# 给指定 Agent 发 Taste 反馈（自动更新 Playbook）
@MarketClaude reddit-hunter taste: 文案太硬了，要更像真人

# 给指定 Agent 推 Prompt 优化
@MarketClaude x-poster prompt: 多用具体数字，少用形容词

# 立即触发汇报
@MarketClaude report now

# 查询 Agent 状态（自然语言提问）
@MarketClaude reddit-hunter 今天跑了多少 leads？
```

## 汇报格式（每天 BJT 09:00 早报 / 18:00 晚报）

```
🌅 GTM 早报 2026-03-30

reddit-hunter ✅ 在线
📍 mac-mini-hangzhou | 👤 Boyuan | 🎯 reddit

• [Why SMBs lose calls on weekends...](https://reddit.com/...)  ❤️8 💬3
• [We tested 5 AI receptionists...](https://reddit.com/...) ❤️12 💬7

---

x-poster ✅ 在线
📍 windows-la | 👤 Ivy | 🎯 x linkedin
• [Missed calls cost $X...](https://x.com/...) ❤️14 💬2

💬 点击链接查看详情，@MarketClaude + AgentName + taste: 反馈内容
```

## 架构

```
钉钉群 @MarketClaude
    ↓ Stream WebSocket
orchestrator Mac (dingtalk-mkt-agent)
    ↓ GitHub API
inbox/{agent_name}/*.json
    ↓ 15秒轮询
worker.py（每台目标机器）
    ↓ claude --print
outbox/{agent_name}/*_result.json
    ↑
reporter.py（cron BJT 9:00 / 18:00）
    ↓
钉钉群早晚报
```

## 文件结构

```
scripts/
  bootstrap.sh   # 一键安装入口（curl | bash）
  install.sh     # 主安装脚本（clone 后调用）
  register.py    # 注册到 GitHub agent bus
  worker.py      # 守护进程：15s 轮询 inbox，执行 taste/prompt/command
  reporter.py    # 生成早晚报并推送钉钉

playbooks/
  x_playbook.md        # X 平台品牌声音 + Taste 评分标准
  reddit_playbook.md   # Reddit 平台规范
  linkedin_playbook.md # LinkedIn 平台规范
```
