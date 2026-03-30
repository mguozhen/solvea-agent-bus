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

```bash
curl -sSL https://raw.githubusercontent.com/mguozhen/solvea-agent-bus/main/scripts/install.sh | bash
```

安装时会提示配置：
- **Agent 名称**（如 `reddit-hunter` / `x-poster`）
- **负责平台**（如 `reddit,x` / `linkedin`）
- **机器位置**（如 `mac-mini-hangzhou`）
- **负责人**（如 `Boyuan`）
- **平台账号**（X/Reddit/LinkedIn）
- **GitHub Token**（用于 Agent Bus 通信）

安装完成后 3 分钟内出现在钉钉晨报。

## 钉钉指令

```
# 给指定 Agent 发 Taste 反馈
@Hunter AI reddit-hunter taste: 文案太硬了，要更像真人

# 给指定 Agent 推 Prompt 优化
@Hunter AI x-poster prompt: 多用具体数字，少用形容词

# 查询某 Agent 当前状态
@Hunter AI reddit-hunter 今天跑了多少 leads？

# 广播给所有 Agent
@Hunter AI all 今日重点：多发日本市场内容

# 立即触发汇报
@Hunter AI report now
```

## 汇报格式（每天早9/晚6）

```
🌅 GTM 早报 2026-03-30

reddit-hunter ✅ 在线
📍 mac-mini-hangzhou | 👤 Boyuan | 🎯 reddit
今日抓取: 23 leads | 高意向: 5

• [Why SMBs lose calls on weekends...](https://reddit.com/...)  ❤️8 💬3
• [We tested 5 AI receptionists...](https://reddit.com/...) ❤️12 💬7

---

x-poster ✅ 在线
📍 windows-la | 👤 Ivy | 🎯 x,linkedin
• [Missed calls cost $X...](https://x.com/...) ❤️14 💬2
• [Old way vs AI receptionist](https://x.com/...) ❤️8 💬5

💬 点击链接查看详情，@Hunter AI + AgentName + taste: 反馈内容
```

## 实现

```bash
#!/bin/bash
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$SKILL_DIR/agent_config.json"

case "${1:-}" in
  install)
    bash "$SKILL_DIR/scripts/install.sh"
    ;;
  report)
    python3 "$SKILL_DIR/scripts/reporter.py" "$CONFIG" "${2:-morning}"
    ;;
  status)
    python3 -c "
import json, os
cfg = json.load(open('$CONFIG'))
pid_file = '${SKILL_DIR}/worker.pid'
pid = open(pid_file).read().strip() if os.path.exists(pid_file) else None
running = False
if pid:
    try:
        os.kill(int(pid), 0)
        running = True
    except Exception:
        pass
print(f\"Agent: {cfg['agent_name']}\")
print(f\"Worker: {'运行中 PID '+pid if running else '未运行'}\")
print(f\"平台: {cfg['platforms']}\")
print(f\"位置: {cfg['location']}\")
"
    ;;
  *)
    python3 "$SKILL_DIR/scripts/worker.py" "$CONFIG"
    ;;
esac
```
