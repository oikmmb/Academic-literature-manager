"""一键启动：uvicorn 后台线程 + pywebview 桌面窗口（--browser 用浏览器调试）。"""
import argparse
import os
import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn

if not getattr(sys, "frozen", False):
    # 源码运行：把 server/ 加入 sys.path；打包后 app 模块已在 PYZ 中
    SERVER_DIR = Path(__file__).resolve().parent / "server"
    sys.path.insert(0, str(SERVER_DIR))

from app.main import app, quit_event  # noqa: E402


def _log(msg: str) -> None:
    """--windowed 打包时 sys.stdout 为 None，print 会抛异常。"""
    if sys.stdout:
        print(msg)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_ready(url: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            # trust_env=False：本机直连，不走系统代理（否则 localhost 会被代理拦截）
            if httpx.get(f"{url}health", timeout=1, trust_env=False).status_code == 200:
                return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("服务启动超时")


def main():
    # --windowed 打包双击启动时无控制台，sys.stdout/stderr 为 None，
    # uvicorn 日志配置会调 stdout.isatty() 崩溃 —— 兜底为 devnull
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true", help="用浏览器打开而不是桌面窗口")
    args = parser.parse_args()

    # LIT_PORT 环境变量可固定端口（打包验证/诊断用），默认自动找空闲端口
    port = int(os.environ.get("LIT_PORT", 0)) or find_free_port()
    url = f"http://127.0.0.1:{port}/"

    # log_config=None：不初始化 uvicorn 的日志 formatter（windowed 下无终端语义）
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    wait_ready(url)

    # 看门狗：前端退出按钮 → /api/v1/app/quit → 关停 uvicorn
    def watch_quit():
        quit_event.wait()
        server.should_exit = True
    threading.Thread(target=watch_quit, daemon=True).start()

    _log(f"文献管家已启动：{url}")
    if args.browser:
        import webbrowser
        webbrowser.open(url)
        while not server.should_exit:
            time.sleep(1)
    else:
        import webview
        window = webview.create_window("文献管家", url, width=1280, height=860, min_size=(960, 640))
        window.events.closed += lambda: setattr(server, "should_exit", True)
        webview.start(gui="edgechromium")
        server.should_exit = True
        thread.join(timeout=3)


if __name__ == "__main__":
    main()
