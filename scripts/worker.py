#!/usr/bin/env python3
"""
Solvea Social Monitor — Worker Daemon
每台机器上跑的守护进程：
- 每 2 分钟轮询 GitHub inbox，执行任务（taste/prompt/command）
- 每 5 分钟更新心跳
- 早 9 / 晚 6 触发日报（由 orchestrator Mac 执行，worker 提供数据）
"""
import json, sys, os, time, subprocess, urllib.request, urllib.error, base64
from datetime import datetime, timezone

CONFIG = json.load(open(sys.argv[1]))
TOKEN  = CONFIG["github_token"]
REPO   = CONFIG["github_repo"]
NAME   = CONFIG["agent_name"]
WORK_DIR = os.path.expanduser("~/reddit-matrix-operator")
CLAUDE_BIN = "/opt/homebrew/bin/claude"

POLL_INTERVAL  = 15    # 15 秒（GitHub API 5000次/小时，完全够用）
HEARTBEAT_INTERVAL = 120  # 2 分钟

_last_heartbeat = 0
_processed_tasks = set()


# ── GitHub helpers ─────────────────────────────────────────────────────────────

def gh_api(method, path, data=None):
    url  = f"https://api.github.com/repos/{REPO}/{path}"
    body = json.dumps(data).encode() if data else None
    req  = urllib.request.Request(url, data=body, method=method,
           headers={"Authorization": f"token {TOKEN}",
                    "Accept": "application/vnd.github.v3+json",
                    "Content-Type": "application/json",
                    "User-Agent": f"solvea-agent/{NAME}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}"), e.code

def read_file(path):
    data, status = gh_api("GET", f"contents/{path}")
    if status != 200:
        return None, None
    content = base64.b64decode(data["content"]).decode()
    return content, data["sha"]

def write_file(path, content, message, sha=None):
    b64 = base64.b64encode(content.encode()).decode()
    payload = {"message": message, "content": b64}
    if sha:
        payload["sha"] = sha
    gh_api("PUT", f"contents/{path}", payload)

def list_dir(path):
    data, status = gh_api("GET", f"contents/{path}")
    if status != 200 or not isinstance(data, list):
        return []
    return [f for f in data if f["name"] != ".gitkeep"]


# ── Heartbeat ──────────────────────────────────────────────────────────────────

def update_heartbeat(status="online", current_task=None):
    path = f"agents/{NAME}.json"
    existing, _ = read_file(path)
    record = json.loads(existing) if existing else {}
    record.update({
        "status":       status,
        "last_seen":    datetime.now(timezone.utc).isoformat(),
        "current_task": current_task,
        "agent_name":   NAME,
        "location":     CONFIG.get("location", ""),
        "platforms":    CONFIG.get("platforms", ""),
        "accounts":     CONFIG.get("accounts", {}),
        "owner":        CONFIG.get("owner", ""),
    })
    _, sha = read_file(path)
    write_file(path, json.dumps(record, indent=2, ensure_ascii=False),
               f"heartbeat: {NAME}", sha)


# ── Task execution ─────────────────────────────────────────────────────────────

def run_claude(prompt, workdir=WORK_DIR):
    """调用 claude --print 执行任务，返回结果文本"""
    try:
        result = subprocess.run(
            [CLAUDE_BIN, "--print", "--dangerously-skip-permissions", prompt],
            capture_output=True, text=True, timeout=180, cwd=workdir
        )
        return result.stdout.strip() or result.stderr.strip()[:500]
    except subprocess.TimeoutExpired:
        return "⚠️ 超时（180s）"
    except Exception as e:
        return f"⚠️ 执行失败: {e}"

def handle_task(task):
    """处理一条任务"""
    task_type = task.get("type", "command")
    payload   = task.get("payload", "")
    task_id   = task.get("id", "")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 执行任务 {task_id} type={task_type}")

    if task_type == "taste":
        # 更新 playbook 的 Taste 学习部分
        platforms = str(CONFIG.get("platforms", "")).split()
        for platform in platforms:
            playbook_path = f"playbooks/{platform}_playbook.md"
            content, sha = read_file(playbook_path)
            if content:
                prompt = f"""你是 Solvea 的内容策略师。

当前 {platform} Playbook：
{content[:2000]}

新的 Taste 反馈：
{payload}

请更新 Playbook 末尾的「今日学习」章节，把这条反馈提炼为 1-3 条具体可执行的规则。
只输出完整的更新后 Playbook 内容，不要额外说明。"""
                updated = run_claude(prompt)
                if updated and len(updated) > 100:
                    write_file(playbook_path, updated,
                               f"taste update: {NAME} {task_id}", sha)
        result = f"✅ Taste 反馈已更新到 Playbook"

    elif task_type == "prompt":
        # 更新 agent 的 prompt 策略
        prompt = f"""Solvea GTM Agent 收到 prompt 优化指令：
{payload}

请根据这个指令，生成 3 条具体的内容创作规则，格式为 Markdown 列表。"""
        result = run_claude(prompt)

    elif task_type == "command":
        # 通用 claude 执行
        result = run_claude(payload)

    elif task_type == "report_request":
        # 生成本机状态报告（用于早晚汇报）
        result = generate_status_report()

    else:
        result = f"未知任务类型: {task_type}"

    return result


def generate_status_report():
    """生成本机状态数据（给 orchestrator 汇总用）"""
    platforms = str(CONFIG.get("platforms", "")).split()
    report = {
        "agent_name": NAME,
        "location":   CONFIG.get("location", ""),
        "owner":      CONFIG.get("owner", ""),
        "platforms":  platforms,
        "accounts":   CONFIG.get("accounts", {}),
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "posts_today": [],   # 由各平台脚本填充
        "status":     "online",
    }

    # 尝试读取今日发帖记录（各平台 Agent 自己写的）
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.expanduser(f"~/agent_posts_{today}.json")
    if os.path.exists(log_path):
        try:
            report["posts_today"] = json.load(open(log_path))
        except Exception:
            pass

    return json.dumps(report, ensure_ascii=False)


# ── Main poll loop ─────────────────────────────────────────────────────────────

def poll_inbox():
    """检查 inbox，执行新任务"""
    tasks = list_dir(f"inbox/{NAME}")
    for task_file in tasks:
        fname = task_file["name"]
        if fname in _processed_tasks or fname == ".gitkeep":
            continue

        content, sha = read_file(f"inbox/{NAME}/{fname}")
        if not content:
            continue

        try:
            task = json.loads(content)
        except Exception:
            task = {"type": "command", "payload": content, "id": fname}

        # 执行
        update_heartbeat(status="working", current_task=fname)
        result = handle_task(task)

        # 写结果到 outbox
        result_file = fname.replace(".json", "_result.json")
        result_data = {
            "task_id":     task.get("id", fname),
            "agent":       NAME,
            "result":      result,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        write_file(f"outbox/{NAME}/{result_file}",
                   json.dumps(result_data, indent=2, ensure_ascii=False),
                   f"result: {NAME} {fname}")

        _processed_tasks.add(fname)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 完成 {fname}")


def main():
    global _last_heartbeat
    print(f"[{NAME}] Worker 启动 | 位置: {CONFIG.get('location')} | 平台: {CONFIG.get('platforms')}")
    update_heartbeat()

    while True:
        now = time.time()
        try:
            poll_inbox()
        except Exception as e:
            print(f"[ERROR] poll_inbox: {e}")

        if now - _last_heartbeat > HEARTBEAT_INTERVAL:
            try:
                update_heartbeat()
                _last_heartbeat = now
            except Exception as e:
                print(f"[ERROR] heartbeat: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
