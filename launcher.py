#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
통합 스튜디오 런처 (studio-launcher)
-----------------------------------
`tools/` 안의 네 로컬 서버를 한 번에 켜고, 통합 허브를 브라우저로 열어 줍니다.

    tts-studio      http://127.0.0.1:8765   대본 -> AI 음성(.mp3) + 자막(.srt)
    shorts-maker    http://127.0.0.1:8766   짤 + 음성 + 자막 -> 9:16 mp4
    coupas-hunter   http://127.0.0.1:8767   쿠팡 가성비 상품 + 4채널 링크
    video-cutter    http://127.0.0.1:8768   영상 최대 5개 구간 자르기 + 합치기
    허브(이 파일)    http://127.0.0.1:8770   네 서버 상태 확인 + 바로가기

동작 방식
  * 이미 켜져 있는 서버는 그대로 씁니다. (같은 서버를 두 번 켜지 않음)
  * 포트가 다른 프로그램에 잡혀 있으면 그 사실을 알려 줍니다.
  * 각 서버의 화면은 이 창(숨김)에서 돌아가고, 로그는 logs/<도구>.log 에 쌓입니다.
  * 이 창을 닫거나 Ctrl+C 를 누르면 같이 켠 서버도 정리합니다.

실행
  python launcher.py               서버 4개 + 허브를 켜고 브라우저를 엽니다
  python launcher.py --no-open     브라우저는 열지 않습니다
  python launcher.py --stop        이 런처가 켠 서버와 허브를 끕니다

Python 3.9 이상, 표준 라이브러리만 사용합니다. (도구별 패키지는 실행하기.bat 이 설치)
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = BASE_DIR / "tools"
LOG_DIR = BASE_DIR / "logs"
PID_FILE = LOG_DIR / "launcher.json"

HUB_HOST = "127.0.0.1"
HUB_PORT = 8770
SERVER_VERSION = "1.0.0"
HEALTH_TIMEOUT = 1.2
START_WAIT = 25.0

# 서버 4종 정의 — 포트와 브라우저 자동 열기 끄기 옵션은 각 도구 사양 그대로
TOOLS = [
    {
        "id": "tts-studio",
        "name": "TTS 스튜디오",
        "port": 8765,
        "args": ["--no-open"],
        "modules": ["edge_tts"],
        "hint": "edge-tts",
    },
    {
        "id": "shorts-maker",
        "name": "쇼츠 메이커",
        "port": 8766,
        "args": ["--no-open"],
        "modules": ["imageio_ffmpeg", "PIL"],
        "hint": "imageio-ffmpeg · Pillow",
    },
    {
        "id": "coupas-hunter",
        "name": "쿠파스 헌터",
        "port": 8767,
        "args": ["--no-browser"],
        "modules": [],
        "hint": "",
    },
    {
        "id": "video-cutter",
        "name": "영상 컷 편집기",
        "port": 8768,
        "args": ["--no-open"],
        "modules": ["imageio_ffmpeg"],
        "hint": "imageio-ffmpeg",
    },
]
TOOL_BY_ID = {t["id"]: t for t in TOOLS}

_STATE_LOCK = threading.Lock()
_STATE = {
    "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "hub": {"port": HUB_PORT, "pid": os.getpid()},
    "tools": {},          # id -> {"pid": int|None, "owned": bool, "note": str, "error": str}
    "shutting_down": False,
    "notes": [],
}
_PROC: dict[str, subprocess.Popen] = {}
_STOP_EVENT = threading.Event()
_HUB_SERVER: ThreadingHTTPServer | None = None


# ───────────────────────────── 공용 도우미 ─────────────────────────────

def log(msg: str) -> None:
    print("[런처] " + str(msg), flush=True)


def warn(msg: str) -> None:
    print("[런처] ! " + str(msg), flush=True)


def http_json(url: str, timeout: float = HEALTH_TIMEOUT) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            if getattr(res, "status", 200) != 200:
                return None
            data = res.read().decode("utf-8", "replace")
        obj = json.loads(data)
        return obj if isinstance(obj, dict) else None
    except Exception:  # noqa: BLE001
        return None


def health(port: int, timeout: float = HEALTH_TIMEOUT) -> dict | None:
    return http_json("http://%s:%d/health" % (HUB_HOST, port), timeout)


def port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((HUB_HOST, port)) == 0


def tail_log(tool_id: str, limit: int = 600) -> str:
    path = LOG_DIR / (tool_id + ".log")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    text = text.strip()
    return text[-limit:] if text else ""


def which_python() -> str:
    return sys.executable or "python"


def modules_ok(tool: dict) -> bool:
    """이 파이썬(가상환경)에 도구 패키지가 들어 있는지."""
    if not tool["modules"]:
        return True
    code = "import " + ", ".join(tool["modules"])
    try:
        return subprocess.run([which_python(), "-c", code],
                              capture_output=True, timeout=30).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def kill_pid(pid: int | None) -> None:
    if not pid:
        return
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, timeout=15)
        except Exception:  # noqa: BLE001
            pass
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        try:
            out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid],
                                 capture_output=True, timeout=10).stdout
            return str(pid).encode() in out
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def write_pid_file() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with _STATE_LOCK:
        snapshot = {
            "hub": {"pid": os.getpid(), "port": HUB_PORT},
            "started_at": _STATE["started_at"],
            "tools": {
                tid: {"pid": info.get("pid"), "port": TOOL_BY_ID[tid]["port"],
                      "owned": bool(info.get("owned"))}
                for tid, info in _STATE["tools"].items()
            },
        }
    try:
        PID_FILE.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def read_pid_file() -> dict:
    try:
        return json.loads(PID_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def set_tool_state(tool_id: str, **kw) -> None:
    with _STATE_LOCK:
        info = _STATE["tools"].setdefault(tool_id, {"pid": None, "owned": False, "note": "", "error": ""})
        info.update(kw)


# ───────────────────────────── 서버 켜기 ─────────────────────────────

def spawn_tool(tool: dict) -> dict:
    """도구 서버 하나를 켭니다. 반환: 이 도구의 상태."""
    tid = tool["id"]
    port = tool["port"]
    server = TOOLS_DIR / tid / "server.py"

    existing = health(port)
    if existing:
        set_tool_state(tid, pid=None, owned=False, note="이미 실행 중이던 서버를 그대로 씁니다.", error="")
        pid = None
        info = read_pid_file().get("tools", {}).get(tid, {})
        if info.get("pid") and pid_alive(info.get("pid")):
            set_tool_state(tid, pid=info["pid"])
        return {"ok": True, "reused": True}

    if port_busy(port):
        msg = "포트 %d 는 다른 프로그램이 쓰고 있어요." % port
        set_tool_state(tid, pid=None, owned=False, note="", error=msg)
        warn("%s — %s" % (tool["name"], msg))
        return {"ok": False, "error": msg, "conflict": True}

    if not server.is_file():
        msg = "tools/%s/server.py 가 없습니다. ZIP 압축을 제대로 풀었는지 확인해 주세요." % tid
        set_tool_state(tid, pid=None, owned=False, note="", error=msg)
        warn("%s — %s" % (tool["name"], msg))
        return {"ok": False, "error": msg, "conflict": False}

    if not modules_ok(tool):
        warn("%s — %s 패키지가 아직 없어요. 실행하기.bat 을 다시 실행하면 설치됩니다." % (tool["name"], tool["hint"]))

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / (tid + ".log")
    log_handle = open(log_path, "ab", buffering=0)
    cmd = [which_python(), "-u", str(server), "--port", str(port), *tool["args"]]
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(server.parent),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            **kwargs,
        )
    except Exception as exc:  # noqa: BLE001
        msg = "서버를 시작하지 못했습니다: %s" % exc
        set_tool_state(tid, pid=None, owned=False, note="", error=msg)
        warn("%s — %s" % (tool["name"], msg))
        return {"ok": False, "error": msg, "conflict": False}

    _PROC[tid] = proc
    set_tool_state(tid, pid=proc.pid, owned=True, note="", error="")
    return {"ok": True, "reused": False, "pid": proc.pid}


def wait_until_ready(tool: dict) -> bool:
    port = tool["port"]
    deadline = time.time() + START_WAIT
    while time.time() < deadline:
        if health(port):
            return True
        proc = _PROC.get(tool["id"])
        if proc is not None and proc.poll() is not None:
            err = tail_log(tool["id"])
            set_tool_state(tool["id"], error=(err or "서버가 바로 종료되었습니다."))
            return False
        time.sleep(0.35)
    return False


# ───────────────────────────── 상태 ─────────────────────────────

def tool_status(tool: dict) -> dict:
    tid = tool["id"]
    data = health(tool["port"])
    with _STATE_LOCK:
        info = dict(_STATE["tools"].get(tid, {}))
    proc = _PROC.get(tid)
    running = bool(proc and proc.poll() is None)
    detail = ""
    if data:
        if tid == "tts-studio":
            eng = data.get("edge_tts")
            if eng:
                detail = "edge-tts %s · 목소리 %d종" % (eng, len(data.get("voices") or []))
                if data.get("gtts"):
                    detail += " · 번역기 포함"
            else:
                detail = "edge-tts 미설치 — 실행하기.bat 을 다시 실행해 주세요"
        elif tid == "shorts-maker":
            detail = ("ffmpeg %s · 1080×1920" % data.get("ffmpeg")) if data.get("ffmpeg") \
                else "ffmpeg 준비 안 됨 — 실행하기.bat 을 다시 실행해 주세요"
        elif tid == "coupas-hunter":
            if data.get("keySet"):
                detail = "쿠팡 키 등록됨 · %s" % (data.get("keyHint") or "")
            else:
                detail = "쿠팡 파트너스 키 등록 필요"
        elif tid == "video-cutter":
            detail = ("ffmpeg %s · 최대 %d개" % (data.get("ffmpeg"), data.get("maxClips") or 5)) \
                if data.get("ffmpegReady") else "ffmpeg 준비 안 됨 — 실행하기.bat 을 다시 실행해 주세요"
    return {
        "id": tid,
        "name": tool["name"],
        "port": tool["port"],
        "url": "http://%s:%d/" % (HUB_HOST, tool["port"]),
        "online": bool(data),
        "health": data,
        "detail": detail,
        "pid": info.get("pid") if (running or info.get("owned")) else info.get("pid"),
        "managed": bool(running),
        "note": info.get("note", ""),
        "error": info.get("error", ""),
    }


def snapshot() -> dict:
    return {
        "ok": True,
        "app": "studio-launcher",
        "version": SERVER_VERSION,
        "hub": {"port": HUB_PORT, "pid": os.getpid(), "started_at": _STATE["started_at"]},
        "tools": [tool_status(t) for t in TOOLS],
    }


# ───────────────────────────── 허브 서버 ─────────────────────────────

class HubHandler(SimpleHTTPRequestHandler):
    server_version = "StudioLauncher/%s" % SERVER_VERSION

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def log_message(self, fmt, *args):  # 콘솔을 조용하게
        pass

    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "86400")

    def json_out(self, obj, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def end_headers(self):
        # 허브 파일은 항상 새로 받도록 (수정 뒤에도 바로 반영)
        self.send_header("Cache-Control", "no-store")
        self.cors()
        super().end_headers()

    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        if path in ("/api/status", "/health"):
            return self.json_out(snapshot())
        return super().do_GET()

    def do_POST(self):  # noqa: N802
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8", "replace") or "{}")
        except Exception:  # noqa: BLE001
            payload = {}

        if path == "/api/start":
            tid = str(payload.get("tool") or "")
            tool = TOOL_BY_ID.get(tid)
            if not tool:
                return self.json_out({"ok": False, "error": "알 수 없는 도구입니다."}, 400)
            result = spawn_tool(tool)
            if result.get("ok"):
                wait_until_ready(tool)
            return self.json_out({"ok": bool(result.get("ok")), "result": result,
                                  "status": tool_status(tool)}, 200 if result.get("ok") else 409)

        if path == "/api/shutdown":
            result = stop_managed()
            names = [TOOL_BY_ID[t]["name"] for t in result["stopped"] if t in TOOL_BY_ID]
            self.json_out({
                "ok": True,
                "stopped": names,
                "remaining": result["remaining"],
                "message": ("%s를 정리했습니다." % ", ".join(names)) if names else "이 런처가 켠 서버가 없습니다.",
            })
            threading.Thread(target=finish_shutdown, name="shutdown", daemon=True).start()
            return

        return self.json_out({"ok": False, "error": "알 수 없는 요청입니다."}, 404)


def start_hub() -> bool:
    global _HUB_SERVER
    # 이미 런처가 떠 있으면 그 허브를 그대로 사용
    existing = http_json("http://%s:%d/api/status" % (HUB_HOST, HUB_PORT), 0.8)
    if existing and existing.get("app") == "studio-launcher":
        log("이미 실행 중인 런처를 찾았습니다. (http://%s:%d/)" % (HUB_HOST, HUB_PORT))
        return False
    try:
        _HUB_SERVER = ThreadingHTTPServer((HUB_HOST, HUB_PORT), HubHandler)
    except OSError as exc:
        warn("허브 포트 %d 를 열지 못했습니다: %s" % (HUB_PORT, exc))
        return False
    _HUB_SERVER.daemon_threads = True
    threading.Thread(target=_HUB_SERVER.serve_forever, name="hub", daemon=True).start()
    return True


# ───────────────────────────── 종료 ─────────────────────────────

def stop_managed() -> dict:
    """이 런처가 켠 서버만 정리하고, 그래도 남아 있는 서버를 알려 줍니다."""
    stopped: list[str] = []
    for tid, proc in list(_PROC.items()):
        if proc.poll() is None:
            kill_pid(proc.pid)
            stopped.append(tid)
    # 이 런처가 관리하던 것으로 pid 파일에 적힌 것도 정리
    data = read_pid_file()
    for tid, info in (data.get("tools") or {}).items():
        if info.get("owned") and info.get("pid") and tid not in stopped:
            kill_pid(info.get("pid"))
            stopped.append(tid)
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass
    time.sleep(0.5)
    remaining = [t["name"] for t in TOOLS if health(t["port"], 0.4)]
    return {"stopped": stopped, "remaining": remaining}


def finish_shutdown() -> None:
    _STOP_EVENT.set()
    if _HUB_SERVER is not None:
        threading.Timer(0.2, _HUB_SERVER.shutdown).start()


def shutdown_all(reason: str = "") -> None:
    with _STATE_LOCK:
        if _STATE["shutting_down"]:
            return
        _STATE["shutting_down"] = True
    if reason:
        log(reason)
    result = stop_managed()
    if result["remaining"]:
        log("이 런처가 켜지 않은 서버는 그대로 둡니다: " + ", ".join(result["remaining"]))
    finish_shutdown()


def install_console_handlers() -> None:
    def _graceful(signum, frame):  # noqa: ARG001
        shutdown_all("종료 신호를 받았습니다. 서버를 정리하는 중...")

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _graceful)
        except Exception:  # noqa: BLE001
            pass
    if os.name == "nt":
        try:
            import ctypes
            prototype = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)

            def _console_event(ctrl_type):
                shutdown_all("창이 닫혀 서버를 정리하는 중...")
                time.sleep(0.4)
                return True

            handler = prototype(_console_event)
            ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, True)
            globals()["_console_handler_ref"] = handler  # 콜백이 GC 되지 않도록 유지
        except Exception:  # noqa: BLE001
            pass


# ───────────────────────────── --stop ─────────────────────────────

def stop_everything() -> int:
    data = read_pid_file()
    stopped = []
    for tid, info in (data.get("tools") or {}).items():
        pid = info.get("pid")
        if pid and info.get("owned") and pid_alive(pid):
            kill_pid(pid)
            stopped.append("%s (pid %s)" % (tid, pid))
    hub = (data.get("hub") or {})
    if hub.get("pid") and pid_alive(hub["pid"]) and hub["pid"] != os.getpid():
        kill_pid(hub["pid"])
        stopped.append("허브 (pid %s)" % hub["pid"])
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass
    if stopped:
        log("정리했습니다: " + ", ".join(stopped))
    else:
        running = [t["name"] for t in TOOLS if health(t["port"], 0.6)]
        if running:
            log("이 런처가 켠 서버는 없습니다. 이미 켜져 있는 서버: " + ", ".join(running))
            log("그 서버들은 각 도구의 창에서 직접 끄거나 작업 관리자에서 종료해 주세요.")
        else:
            log("켜져 있는 서버가 없습니다.")
    return 0


# ───────────────────────────── main ─────────────────────────────

def print_banner() -> None:
    print("", flush=True)
    print("=" * 62, flush=True)
    print("   통합 스튜디오 런처 v%s — TTS · 쇼츠 · 쿠파스 · 컷편집 한 번에" % SERVER_VERSION, flush=True)
    print("=" * 62, flush=True)


def print_status_table() -> None:
    print("", flush=True)
    for tool in TOOLS:
        st = tool_status(tool)
        mark = "ON " if st["online"] else "OFF"
        line = "  [%s] %-10s http://127.0.0.1:%d/" % (mark, tool["name"], tool["port"])
        if st["detail"]:
            line += "  — " + st["detail"]
        print(line, flush=True)
        if st["error"]:
            print("        ! " + st["error"].replace("\n", " ")[:180], flush=True)
    print("", flush=True)
    print("  허브: http://127.0.0.1:%d/   (이 창을 닫거나 Ctrl+C 를 누르면 서버도 정리됩니다)" % HUB_PORT,
          flush=True)
    print("  종료가 안 되면 종료하기.bat 을 더블클릭하세요.", flush=True)
    print("", flush=True)


def monitor() -> None:
    """서버가 도중에 죽으면 알려 주고, 상태 변화만 조용히 출력합니다."""
    last: dict[str, bool] = {}
    while not _STOP_EVENT.is_set():
        for tool in TOOLS:
            st = tool_status(tool)
            prev = last.get(tool["id"])
            if prev is not None and prev != st["online"]:
                if st["online"]:
                    log("%s 가 다시 켜졌습니다. (포트 %d)" % (tool["name"], tool["port"]))
                else:
                    tail = tail_log(tool["id"], 300).replace("\n", " ")
                    log("%s 가 꺼졌습니다. 로그: logs/%s.log %s" % (tool["name"], tool["id"], tail[-160:]))
            last[tool["id"]] = st["online"]
        time.sleep(4)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="통합 스튜디오 런처")
    parser.add_argument("--no-open", dest="open_browser", action="store_false", help="브라우저를 열지 않습니다")
    parser.add_argument("--stop", action="store_true", help="이 런처가 켠 서버를 모두 끕니다")
    parser.add_argument("--hub-port", type=int, default=HUB_PORT)
    parser.set_defaults(open_browser=True)
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    if args.stop:
        return stop_everything()

    print_banner()
    install_console_handlers()
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    url = "http://%s:%d/" % (HUB_HOST, args.hub_port)
    already = http_json("http://%s:%d/api/status" % (HUB_HOST, args.hub_port), 0.8)
    if already and already.get("app") == "studio-launcher":
        log("이미 켜져 있는 런처가 있습니다 → " + url)
        log("상태 확인과 꺼진 서버 다시 켜기는 허브 화면에서 하세요.")
        if args.open_browser:
            webbrowser.open(url)
        time.sleep(1.2)
        return 0

    with _STATE_LOCK:
        for tool in TOOLS:
            _STATE["tools"][tool["id"]] = {"pid": None, "owned": False, "note": "", "error": ""}

    log("서버 4종을 확인합니다... (이미 켜져 있으면 그대로 씁니다)")
    for tool in TOOLS:
        spawn_tool(tool)

    pending = [t for t in TOOLS if not health(t["port"], 0.6)]
    if pending:
        log("새로 켜는 서버를 기다리는 중... (%s)" % ", ".join(t["name"] for t in pending))
    for tool in _PROC.keys():
        t = TOOL_BY_ID[tool]
        ok = wait_until_ready(t)
        if ok:
            log("%s 준비 완료 → http://127.0.0.1:%d/" % (t["name"], t["port"]))
        else:
            warn("%s 가 응답하지 않습니다. logs/%s.log 를 확인해 주세요." % (t["name"], t["id"]))

    hub_ours = start_hub()
    if not hub_ours and not http_json("http://%s:%d/api/status" % (HUB_HOST, args.hub_port), 0.8):
        warn("허브 페이지 없이 서버만 켭니다.")

    write_pid_file()
    print_status_table()

    if args.open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    threading.Thread(target=monitor, name="monitor", daemon=True).start()
    try:
        while not _STOP_EVENT.wait(1.0):
            pass
    except KeyboardInterrupt:
        shutdown_all("Ctrl+C — 서버를 정리하는 중...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
