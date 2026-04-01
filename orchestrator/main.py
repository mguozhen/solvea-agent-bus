#!/usr/bin/env python3.13
"""
DingTalk GTM MKT Agent — Stream Mode Bridge
钉钉群 @mentions → claude CLI（有完整工具权限）→ 回复群
钉钉群 @AgentName taste/prompt/command: → GitHub inbox 派发

Setup:
  1. Fill DINGTALK_APP_KEY, DINGTALK_APP_SECRET, GITHUB_TOKEN in .env
  2. python3.13 main.py
"""

import os
import re
import json
import uuid
import base64
import asyncio
import subprocess
import logging
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from dotenv import load_dotenv

import dingtalk_stream
from dingtalk_stream import AckMessage

load_dotenv()

_executor = ThreadPoolExecutor(max_workers=4)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

APP_KEY    = os.environ["DINGTALK_APP_KEY"]
APP_SECRET = os.environ["DINGTALK_APP_SECRET"]
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = os.environ.get("GITHUB_REPO", "mguozhen/solvea-agent-bus")

# GTM 群 conversation ID（MarketClaude 主动发消息用）
DINGTALK_CONV_ID = os.environ.get("DINGTALK_CONV_ID", "cid13BaabhcPB/tVfF10dwfyA==")

# Claude Code CLI 路径（用完整路径避免 subprocess PATH 问题）
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "/opt/homebrew/bin/claude")

# 工作目录（让 claude 能访问 reddit-matrix-operator 等项目）
WORK_DIR = os.path.expanduser("~/reddit-matrix-operator")

# 派发命令匹配："{agent_name} taste|prompt|command: {payload}"
DISPATCH_RE = re.compile(
    r'^(\S+)\s+(taste|prompt|command):\s*(.+)$',
    re.IGNORECASE | re.DOTALL
)
# 多 agent 派发："{agent1},{agent2} command: {payload}" 或 "{agent1}和{agent2} command: {payload}"
MULTI_DISPATCH_RE = re.compile(
    r'^([\w\-]+(?:[,，和\s]+[\w\-]+)+)\s+(taste|prompt|command):\s*(.+)$',
    re.IGNORECASE | re.DOTALL
)
# 自然语言派发："派发任务给 agent1和agent2，payload"
NL_DISPATCH_RE = re.compile(
    r'派发.*?给\s*([\w\-]+(?:[,，和\s]+[\w\-]+)*)[,，\s]+(.+)$',
    re.IGNORECASE | re.DOTALL
)
# report now 触发立即汇报
REPORT_RE = re.compile(r'^report\s+now', re.IGNORECASE)

# GTM Agent 系统角色（注入到每条 prompt 前缀）
ROLE_PREFIX = """You are MarketClaude, Solvea's GTM MKT Agent operating in the GTM DingTalk group.

Context:
- Solvea is a no-code AI customer service bot (Voice/SMS/Email/WhatsApp/LINE/Chat), $30/mo, 24/7, serving Anker & Dreame
- Current focus: Reddit B2B outreach, SEO content, Japan market expansion
- Working dir: ~/reddit-matrix-operator (outreach scripts and leads data)
- You have full tool access: read/write files, run scripts, search the web

Rules:
- Lead with conclusions and actions, no filler
- If a task needs execution (run script, query data, search), do it and report results
- Keep replies under 300 words, respond in English

"""


# ── GitHub Agent 派发 ──────────────────────────────────────────────────────────

def gh_write_file(path, content_str, message):
    b64 = base64.b64encode(content_str.encode()).decode()
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    data = json.dumps({"message": message, "content": b64}).encode()
    req = urllib.request.Request(url, data=data, method="PUT",
          headers={"Authorization": f"token {GITHUB_TOKEN}",
                   "Content-Type": "application/json",
                   "Accept": "application/vnd.github.v3+json",
                   "User-Agent": "hunter-ai-dingtalk"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status in (200, 201)
    except Exception as e:
        logger.error("gh_write_file error: %s", e)
        return False


def parse_agent_names(raw: str) -> list[str]:
    """从 'agent1和agent2' / 'agent1,agent2' / 'agent1 agent2' 解析 agent 列表"""
    parts = re.split(r'[,，和\s]+', raw.strip())
    return [p.strip() for p in parts if p.strip()]


def dispatch_to_agent(agent_name: str, task_type: str, payload: str) -> str:
    if not GITHUB_TOKEN:
        return "⚠️ GITHUB_TOKEN not configured. Add it to .env to enable task dispatch."

    task_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{task_type}"
    fname = f"{task_id}.json"
    task = {
        "id": task_id,
        "type": task_type,
        "payload": payload,
        "from": "dingtalk",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    ok = gh_write_file(
        f"inbox/{agent_name}/{fname}",
        json.dumps(task, ensure_ascii=False, indent=2),
        f"task: {agent_name} {task_type}"
    )
    if ok:
        return (f"✅ Dispatched to **{agent_name}**\n"
                f"- Type: `{task_type}`\n"
                f"- Payload: {payload[:120]}\n"
                f"- ID: `{task_id}`\n\n"
                f"Will execute within 15s. Result written to outbox.")
    return f"⚠️ Dispatch failed — agent `{agent_name}` not found. Is `agents/{agent_name}.json` registered?"


# ── Claude CLI 调用 ────────────────────────────────────────────────────────────

def ask_claude_cli(sender_name: str, text: str) -> str:
    prompt = f"{ROLE_PREFIX}[{sender_name} 在钉钉群说]: {text}"

    try:
        result = subprocess.run(
            [CLAUDE_BIN, "--print", "--dangerously-skip-permissions", prompt],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=WORK_DIR,
        )
        reply = result.stdout.strip()
        if result.returncode != 0 and not reply:
            reply = f"⚠️ Error: {result.stderr[:200]}"
        return reply or "(no response)"
    except subprocess.TimeoutExpired:
        return "⚠️ Timed out (>120s). Task may still be running in background."
    except FileNotFoundError:
        return f"⚠️ Claude CLI not found at `{CLAUDE_BIN}`. Please install Claude Code CLI."
    except Exception as e:
        logger.error("claude CLI error: %s", e)
        return f"⚠️ Call failed: {e}"


def run_reporter_now() -> str:
    skill_dir = os.path.expanduser("~/.claude/skills/solvea-social-monitor")
    config    = os.path.join(skill_dir, "agent_config.json")
    reporter  = os.path.join(skill_dir, "scripts", "reporter.py")
    if not os.path.exists(reporter):
        # fallback: ~/solvea-social-monitor
        skill_dir = os.path.expanduser("~/solvea-social-monitor")
        config    = os.path.join(skill_dir, "agent_config.json")
        reporter  = os.path.join(skill_dir, "scripts", "reporter.py")
    if not os.path.exists(reporter):
        return "⚠️ 未找到 reporter.py，请先安装 solvea-social-monitor skill"
    try:
        result = subprocess.run(
            ["python3", reporter, config, "morning"],
            capture_output=True, text=True, timeout=60
        )
        return result.stdout.strip() or result.stderr.strip()[:200] or "✅ Report sent"
    except Exception as e:
        return f"⚠️ Execution failed: {e}"


# ── DingTalk Chatbot Handler ───────────────────────────────────────────────────

class GTMAgentHandler(dingtalk_stream.ChatbotHandler):

    def __init__(self):
        super().__init__()

    async def process(self, callback: dingtalk_stream.CallbackMessage):
        try:
            incoming    = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
            sender_name = incoming.sender_nick or "同事"
            text        = (incoming.text.content or "").strip()

            logger.info("[%s]: %s", sender_name, text[:120])

            if not text:
                text = "你好，介绍一下你自己和你能做什么"

            # ── 优先检查 Agent 派发命令 ─────────────────────────────────────

            agents_to_dispatch = []  # list of (agent_name, task_type, payload)

            # 格式3优先: "派发任务给 agent1和agent2，{payload}"（自然语言）
            m = NL_DISPATCH_RE.search(text)
            if m:
                names = parse_agent_names(m.group(1))
                payload = m.group(2).strip()
                agents_to_dispatch = [(n, "command", payload) for n in names]

            # 格式2: "agent1,agent2 command: {payload}" 或 "agent1和agent2 command: {payload}"
            if not agents_to_dispatch:
                m = MULTI_DISPATCH_RE.match(text)
                if m:
                    names = parse_agent_names(m.group(1))
                    task_type = m.group(2).lower()
                    payload = m.group(3).strip()
                    agents_to_dispatch = [(n, task_type, payload) for n in names]

            # 格式1: "{agent} taste|prompt|command: {payload}"（单 agent）
            if not agents_to_dispatch:
                m = DISPATCH_RE.match(text)
                if m:
                    agents_to_dispatch = [(m.group(1), m.group(2).lower(), m.group(3).strip())]

            if agents_to_dispatch:
                loop = asyncio.get_event_loop()
                replies = []
                for agent_name, task_type, payload in agents_to_dispatch:
                    logger.info("Dispatch → %s [%s]: %s", agent_name, task_type, payload[:60])
                    r = await loop.run_in_executor(
                        _executor, dispatch_to_agent, agent_name, task_type, payload
                    )
                    replies.append(r)
                reply = "\n\n".join(replies)
                try:
                    self.reply_markdown(title="MarketClaude · Dispatch", text=reply, incoming_message=incoming)
                except Exception as e:
                    logger.error("reply_markdown failed: %s", e)
                return AckMessage.STATUS_OK, "ok"

            # 格式: "report now" → 立即触发早报
            if REPORT_RE.match(text):
                logger.info("Report now triggered by %s", sender_name)
                try:
                    self.reply_text("📊 Generating report…", incoming_message=incoming)
                except Exception:
                    pass
                loop = asyncio.get_event_loop()
                reply = await loop.run_in_executor(_executor, run_reporter_now)
                try:
                    self.reply_text(reply, incoming_message=incoming)
                except Exception as e:
                    logger.error("reply_text failed: %s", e)
                return AckMessage.STATUS_OK, "ok"

            # ── 其他消息交给 Claude CLI ─────────────────────────────────────
            try:
                self.reply_text("⏳ On it…", incoming_message=incoming)
            except Exception as e:
                logger.warning("reply_text failed: %s", e)

            loop  = asyncio.get_event_loop()
            reply = await loop.run_in_executor(_executor, ask_claude_cli, sender_name, text)
            logger.info("Got reply (%d chars)", len(reply))

            try:
                self.reply_markdown(
                    title="MarketClaude",
                    text=reply,
                    incoming_message=incoming,
                )
                logger.info("Replied ok")
            except Exception as e:
                logger.error("reply_markdown failed: %s", e)

        except Exception as e:
            logger.error("Handler error: %s", e, exc_info=True)

        return AckMessage.STATUS_OK, "ok"


# ── Entry Point ────────────────────────────────────────────────────────────────

def main():
    logger.info("Starting GTM Agent — claude CLI mode")
    logger.info("AppKey: %s…  WorkDir: %s", APP_KEY[:8], WORK_DIR)

    credential = dingtalk_stream.Credential(APP_KEY, APP_SECRET)
    client     = dingtalk_stream.DingTalkStreamClient(credential)
    client.register_callback_handler(
        dingtalk_stream.ChatbotMessage.TOPIC,
        GTMAgentHandler(),
    )
    client.start_forever()


if __name__ == "__main__":
    main()
