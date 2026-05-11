"""Connectivity check for the two MVP integrations.

Usage:
  python src/doctor.py            # check both
  python src/doctor.py smtp       # only SMTP
  python src/doctor.py dingtalk   # only DingTalk
"""
from __future__ import annotations

import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str, hint: str = "") -> None:
    print(f"  {RED}✗{RESET} {msg}")
    if hint:
        print(f"    {DIM}{hint}{RESET}")


def check_smtp() -> bool:
    print("\n[SMTP / Gmail]")
    user = os.environ.get("SMTP_USER")
    pw = os.environ.get("SMTP_PASS")
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))

    if not user or not pw or pw.startswith("xxxx"):
        fail("SMTP_USER / SMTP_PASS 未配置",
             "在 .env 填好账号密码 (Gmail 用 App Password, 不是登录密码)")
        return False

    try:
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.ehlo()
            s.starttls()
            s.login(user, pw)
            ok(f"连接 + 登录 {host}:{port} 成功 ({user})")
    except smtplib.SMTPAuthenticationError as e:
        fail(f"认证失败: {e.smtp_code} {e.smtp_error.decode(errors='ignore') if isinstance(e.smtp_error, bytes) else e.smtp_error}",
             "Gmail: 必须用 App Password (16 位)，不是 Google 账号密码")
        return False
    except Exception as e:
        fail(f"连接失败: {type(e).__name__}: {e}")
        return False

    # send a test mail to self
    msg = MIMEText("wx-schedule SMTP doctor: 这是一封自检邮件，收到表示 SMTP 通了。", "plain", "utf-8")
    msg["Subject"] = "[wx-schedule] SMTP self-test"
    msg["From"] = formataddr((os.environ.get("SMTP_FROM_NAME", user), user))
    msg["To"] = user
    msg["Date"] = formatdate(localtime=True)
    try:
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.starttls()
            s.login(user, pw)
            s.sendmail(user, [user], msg.as_string())
        ok(f"发送测试邮件到 {user} (查你的 Gmail 收件箱)")
    except Exception as e:
        fail(f"sendmail 失败: {e}")
        return False
    return True


def check_dingtalk() -> bool:
    print("\n[DingTalk Calendar via mcporter]")
    sys.path.insert(0, str(ROOT / "src"))
    import dingtalk

    url = os.environ.get("DINGTALK_CALENDAR_MCP_URL")
    if not url:
        fail("DINGTALK_CALENDAR_MCP_URL 未配置",
             "去 https://mcp.dingtalk.com 找日程/日历 MCP，复制 Streamable HTTP URL 填进 .env")
        return False

    bin_path = dingtalk._bin()
    if not Path(bin_path).exists():
        fail(f"mcporter 不存在: {bin_path}", "运行: bun install -g mcporter")
        return False
    ok(f"mcporter found at {bin_path}")

    try:
        schema = dingtalk.discover()
    except Exception as e:
        fail(f"discover 失败: {e}",
             "URL 格式: https://mcp-streamable.dingtalk.com/sse?token=...; 也可能是 token 失效")
        return False

    tools = [t.get("name") for t in schema.get("tools", []) if t.get("name")]
    if not tools:
        fail(f"MCP server 没暴露任何 tool. 原始返回: {json.dumps(schema, ensure_ascii=False)[:200]}")
        return False
    ok(f"MCP server 暴露 {len(tools)} 个 tool: {', '.join(tools[:8])}{'...' if len(tools) > 8 else ''}")

    list_tool = dingtalk._pick_tool(dingtalk.CANDIDATE_LIST_TOOLS, tools)
    create_tool = dingtalk._pick_tool(dingtalk.CANDIDATE_CREATE_TOOLS, tools)
    if not list_tool:
        fail(f"找不到 list-events 工具", f"实际工具: {tools}. 把对的名字加进 dingtalk.CANDIDATE_LIST_TOOLS")
        return False
    ok(f"list-events tool: {list_tool}")
    if not create_tool:
        fail(f"找不到 create-event 工具", f"实际工具: {tools}. 把对的名字加进 dingtalk.CANDIDATE_CREATE_TOOLS")
        return False
    ok(f"create-event tool: {create_tool}")

    try:
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        events = dingtalk.busy_intervals(now, now + timedelta(days=7))
        ok(f"未来 7 天读到 {len(events)} 个事件")
        for s, e in events[:5]:
            print(f"      {DIM}· {s.isoformat()} → {e.isoformat()}{RESET}")
    except Exception as e:
        fail(f"读日历失败: {e}")
        return False
    return True


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    results = []
    if target in ("all", "smtp"):
        results.append(("SMTP", check_smtp()))
    if target in ("all", "dingtalk"):
        results.append(("DingTalk", check_dingtalk()))

    print("\n" + "=" * 40)
    all_ok = all(r[1] for r in results)
    for name, ok_ in results:
        status = f"{GREEN}OK{RESET}" if ok_ else f"{RED}FAIL{RESET}"
        print(f"  {name}: {status}")
    print("=" * 40)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
