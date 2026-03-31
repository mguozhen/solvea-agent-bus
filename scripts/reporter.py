#!/usr/bin/env python3
"""
Solvea Social Monitor - Reporter
从 GitHub 读取所有 Agent 状态 -> 生成汇报 -> 推送钉钉 (App API / sendmsg)
"""
import json, sys, os, urllib.request, urllib.error, base64
from datetime import datetime, timezone

CONFIG     = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else {}
TOKEN      = CONFIG.get("github_token") or os.environ.get("GITHUB_TOKEN", "")
REPO       = "mguozhen/solvea-agent-bus"
APP_KEY    = CONFIG.get("dingtalk_app_key")    or os.environ.get("DINGTALK_APP_KEY",    "ding3shkntgajgeigymb")
APP_SECRET = CONFIG.get("dingtalk_app_secret") or os.environ.get("DINGTALK_APP_SECRET", "")
CONV_ID    = CONFIG.get("dingtalk_conv_id")    or os.environ.get("DINGTALK_CONV_ID",    "cid13BaabhcPB/tVfF10dwfyA==")
REPORT_TYPE = sys.argv[2] if len(sys.argv) > 2 else "morning"


def gh_get(path):
    url = f"https://api.github.com/repos/{REPO}/{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "solvea-reporter"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return {}, e.code


def list_agents():
    data, status = gh_get("contents/agents")
    if status != 200 or not isinstance(data, list):
        return []
    agents = []
    for f in data:
        if not f["name"].endswith(".json") or f["name"] == ".gitkeep":
            continue
        raw, _ = gh_get(f"contents/agents/{f['name']}")
        if raw and "content" in raw:
            try:
                content = base64.b64decode(raw["content"]).decode()
                agents.append(json.loads(content))
            except Exception:
                pass
    return agents


def read_outbox_results(agent_name):
    data, status = gh_get(f"contents/outbox/{agent_name}")
    if status != 200 or not isinstance(data, list):
        return []
    results = []
    today = datetime.now().strftime("%Y-%m-%d")
    for f in data:
        if today in f["name"] and f["name"].endswith("_result.json"):
            raw, _ = gh_get(f"contents/outbox/{agent_name}/{f['name']}")
            if raw and "content" in raw:
                try:
                    content = base64.b64decode(raw["content"]).decode()
                    results.append(json.loads(content))
                except Exception:
                    pass
    return results


def format_agent_block(agent):
    name      = agent.get("agent_name", "unknown")
    location  = agent.get("location", "?")
    owner     = agent.get("owner", "?")
    platforms = agent.get("platforms", "")
    accounts  = agent.get("accounts", {})
    last_seen = agent.get("last_seen", "")

    try:
        last_dt  = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
        diff_min = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60
        if diff_min < 10:
            status_icon, status_text = "✅", "在线"
        elif diff_min < 60:
            status_icon, status_text = "⚠️", f"{int(diff_min)}分钟前在线"
        else:
            status_icon, status_text = "🔴", f"{int(diff_min/60)}小时无心跳"
    except Exception:
        status_icon, status_text = "❓", "状态未知"

    results  = read_outbox_results(name)
    all_posts = []
    for r in results:
        result_data = r.get("result", "")
        try:
            parsed = json.loads(result_data) if isinstance(result_data, str) else result_data
            if isinstance(parsed, dict) and "posts_today" in parsed:
                all_posts.extend(parsed["posts_today"])
        except Exception:
            pass

    posts_section = ""
    if all_posts:
        posts_section = "\n"
        for p in all_posts[:5]:
            url   = p.get("url", "")
            title = p.get("title", p.get("content", "")[:40])
            likes = p.get("likes", 0)
            cmts  = p.get("comments", 0)
            if url:
                posts_section += f"  - [{title}]({url})"
                if likes or cmts:
                    posts_section += f" ❤️{likes} 💬{cmts}"
                posts_section += "\n"

    account_str = " | ".join(f"{k}: @{v}" for k, v in accounts.items() if v)
    block = f"**{name}** {status_icon} {status_text}\n📍 {location} | 👤 {owner} | 🎯 {platforms}\n{account_str}{posts_section}"
    return block.strip()


def get_access_token():
    """用 AK/SK 换取钉钉 accessToken"""
    url     = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
    payload = json.dumps({"appKey": APP_KEY, "appSecret": APP_SECRET}).encode()
    req     = urllib.request.Request(url, data=payload,
                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        resp = json.loads(r.read())
    token = resp.get("accessToken", "")
    if not token:
        raise RuntimeError(f"accessToken empty, resp={resp}")
    return token


def send_msg(text, title="GTM 汇报"):
    """通过 App API (groupMessages/send) 发送到群"""
    access_token = get_access_token()
    url     = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"
    payload = json.dumps({
        "robotCode":          APP_KEY,
        "openConversationId": CONV_ID,
        "msgKey":             "sampleMarkdown",
        "msgParam":           json.dumps({"title": title, "text": text})
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type":                "application/json",
        "x-acs-dingtalk-access-token": access_token
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        resp = json.loads(r.read())
    if resp.get("processQueryKey") or resp.get("success") is not False:
        return True, resp
    raise RuntimeError(f"send failed: {resp}")


def main():
    now_jst  = datetime.now(timezone.utc)
    date_str = now_jst.strftime("%Y-%m-%d")
    label    = "晚报" if REPORT_TYPE == "evening" else "早报"
    agents   = list_agents()

    if not agents:
        print("⚠️ No agents found")
        return

    blocks = [format_agent_block(a) for a in agents]
    title  = f"GTM {label} {date_str}"
    body   = f"## {title}\n\n" + "\n\n---\n\n".join(blocks)

    if not APP_SECRET:
        print(f"❌ DINGTALK_APP_SECRET 未配置，无法发送")
        return

    try:
        ok, resp = send_msg(body, title=title)
        print(f"✅ {title} 已发送，{len(agents)} 个 Agent")
    except Exception as e:
        print(f"❌ 发送失败: {e}")
        raise


if __name__ == "__main__":
    main()
