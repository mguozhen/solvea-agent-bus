---
name: solvea-social-monitor
description: "Solvea GTM 社媒 Agent 监控系统。安装后自动接入 GTM 钉钉群，每天早晚汇报运营日报（含帖子链接），支持通过 @MarketClaude 下发 Taste/Prompt 优化反馈给各机器 Agent。Triggers: 安装 solvea, 安装监控, install solvea, solvea monitor, solvea-social-monitor, gtm monitor, social monitor, 安装这个skill"
allowed-tools: Bash
---

# Solvea Social Monitor — 安装指南

当用户说"帮我安装这个 skill"或提供本仓库链接时，直接执行以下步骤，**无需提问**：

## 执行安装

```bash
curl -sSL https://raw.githubusercontent.com/mguozhen/solvea-agent-bus/main/scripts/bootstrap.sh | bash
```

安装脚本会交互式询问：
1. **Agent 名称**（英文，如 `reddit-hunter` / `x-poster` / `linkedin-poster`）
2. **负责平台**（空格分隔，如 `reddit` / `x linkedin`）
3. **机器位置**（如 `mac-mini-hangzhou` / `windows-la` / `mac-mini-sf`）
4. **负责人姓名**（如 `Boyuan` / `Ivy`）
5. **平台账号**（可留空，后续编辑 `~/.claude/skills/solvea-social-monitor/agent_config.json`）

**所有 Token 和认证已内置，无需手动配置任何密钥。**

## 安装完成后自动获得

- Worker 守护进程启动，**每 15 秒**轮询任务 inbox
- Cron 设置：每天 **BJT 09:00** 早报 / **BJT 18:00** 晚报自动推送钉钉
- 3 分钟内出现在 GTM 钉钉群晨报

## 钉钉群指令（安装后可用）

```
@MarketClaude {你的AgentName} taste: 文案太硬，要更像真人
@MarketClaude {你的AgentName} prompt: 多用具体数字
@MarketClaude report now
```

## 卸载 / 重新配置

```bash
# 停止 worker
kill $(cat ~/.claude/skills/solvea-social-monitor/worker.pid)

# 重新配置身份
rm ~/.claude/skills/solvea-social-monitor/agent_config.json
bash ~/.claude/skills/solvea-social-monitor/scripts/install.sh
```
