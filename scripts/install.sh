#!/bin/bash
# Solvea Social Monitor — 一键安装脚本
# 安装即可用：钉钉认证已内置，只需填 GitHub Token + Agent 身份
set -e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="$DIR/agent_config.json"

# ── 内置认证信息（无需手动配置）──────────────────────────────────────
DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=0c99a28c3a98fc33dc6d193c66a5d792d1dd9af701238bd7a398b46010fdeae5"
DINGTALK_APP_KEY="ding3shkntgajgeigymb"
DINGTALK_APP_SECRET="f2GBQzDl_dPXsBF9G9Ftsvby5G9JxtpX6kdvD6FfKBxQlOZzMvSbijqdAD0ZM5Nj"
GITHUB_REPO="mguozhen/solvea-agent-bus"

echo "========================================"
echo "  Solvea Social Monitor — Agent Setup"
echo "========================================"
echo ""

# ── 1. 读取或创建 Agent 身份配置 ─────────────────────────────────────

if [ -f "$CONFIG" ]; then
  echo "✅ 已有配置文件，跳过身份设置。"
  AGENT_NAME=$(python3 -c "import json; d=json.load(open('$CONFIG')); print(d['agent_name'])")
  echo "   Agent: $AGENT_NAME"
  echo ""
else
  echo "【第一步：配置 Agent 身份】"
  echo ""
  read -p "Agent 名称（英文，如 reddit-hunter / x-poster）: " AGENT_NAME
  read -p "负责平台（如 reddit / x / linkedin，空格分隔）: " PLATFORMS
  read -p "机器位置（如 mac-mini-hangzhou / windows-la）: " LOCATION
  read -p "负责人（如 Boyuan / Ivy）: " OWNER

  echo ""
  echo "【第二步：配置平台账号】"
  echo "（留空跳过，后续可手动编辑 agent_config.json）"
  read -p "X (Twitter) 账号: " X_ACCOUNT
  read -p "Reddit 账号: " REDDIT_ACCOUNT
  read -p "LinkedIn 账号: " LINKEDIN_ACCOUNT

  echo ""
  echo "【第三步：GitHub Token（用于 Agent Bus 通信）】"
  echo "前往 https://github.com/settings/tokens 新建 Token（需要 repo 权限）"
  read -p "GitHub Token: " GITHUB_TOKEN

  # 写入配置（钉钉认证已内置）
  cat > "$CONFIG" <<EOF
{
  "agent_name": "$AGENT_NAME",
  "platforms": "$PLATFORMS",
  "location": "$LOCATION",
  "owner": "$OWNER",
  "accounts": {
    "x": "$X_ACCOUNT",
    "reddit": "$REDDIT_ACCOUNT",
    "linkedin": "$LINKEDIN_ACCOUNT"
  },
  "github_token": "$GITHUB_TOKEN",
  "github_repo": "$GITHUB_REPO",
  "dingtalk_webhook": "$DINGTALK_WEBHOOK",
  "dingtalk_app_key": "$DINGTALK_APP_KEY",
  "dingtalk_app_secret": "$DINGTALK_APP_SECRET",
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
  echo "✅ 配置已写入 agent_config.json"
fi

echo ""
echo "【注册到 Agent Bus】"
python3 "$DIR/scripts/register.py" "$CONFIG"

echo ""
echo "【启动 Worker 守护进程】"
pkill -f "solvea-social-monitor/scripts/worker.py" 2>/dev/null || true
nohup python3 "$DIR/scripts/worker.py" "$CONFIG" >> "$DIR/worker.log" 2>&1 &
echo $! > "$DIR/worker.pid"
echo "✅ Worker 已启动 (PID $(cat $DIR/worker.pid))"

echo ""
echo "【设置早晚汇报定时任务（每天 BJT 9:00 / 18:00）】"

REPORTER="python3 $DIR/scripts/reporter.py $CONFIG"
MORNING_CRON="0 1 * * * $REPORTER morning >> $DIR/reporter.log 2>&1"
EVENING_CRON="0 10 * * * $REPORTER evening >> $DIR/reporter.log 2>&1"

# 添加到 crontab（去重：先移除旧的，再添加）
(crontab -l 2>/dev/null | grep -v "solvea-social-monitor/scripts/reporter.py"; \
 echo "$MORNING_CRON"; echo "$EVENING_CRON") | crontab -

echo "✅ 定时任务已设置:"
echo "   早报: UTC 01:00 (BJT 09:00) 每天"
echo "   晚报: UTC 10:00 (BJT 18:00) 每天"

echo ""
echo "========================================"
echo "  ✅ $AGENT_NAME 安装完成，已接入 GTM 网络"
echo ""
echo "  钉钉群指令："
echo "  @Hunter AI $AGENT_NAME taste: 反馈内容"
echo "  @Hunter AI $AGENT_NAME prompt: 优化策略"
echo "  @Hunter AI report now  （立即触发汇报）"
echo "========================================"
