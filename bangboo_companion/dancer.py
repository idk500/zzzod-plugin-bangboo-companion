"""桌面舞者引擎：独立线程内运行 tkinter 透明置顶窗口，逐帧播放 GIF。

线程模型
========
- 控制器 (DancerController) 是模块级单例，供工厂事件回调用，全部方法线程安全。
- 舞者线程内创建 Tk 主窗口并跑 mainloop；控制指令通过队列传入。
- 事件回调（od_event_bus 线程池）只往队列放指令，绝不跨线程碰 Tk 对象。

生命周期
========
- 播放 = 一条龙开始运行事件；暂停 = 一条龙停止运行事件（停帧留在原地）。
- 右键菜单可手动退出；一条龙再次启动会重新拉起舞者线程。
"""

from __future__ import annotations

import queue
import threading

from one_dragon.utils.log_utils import log

# 控制指令
CTRL_PLAY = 'play'
CTRL_PAUSE = 'pause'
CTRL_QUIT = 'quit'
CTRL_RELOAD = 'reload'

# GIF 透明区域合成的底色（几乎不可能出现在画面里的暗色）
KEY_COLOR = (1, 1, 1)


class DancerController:
    """线程安全的舞者控制器，模块级单例。"""

    def __init__(self, gif_path: str):
        self._gif_path: str = gif_path
        self._cmd_queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def play(self) -> None:
        """开始跳舞（窗口不存在则拉起，存在则恢复播放）。"""
        self._submit(CTRL_PLAY)

    def pause(self) -> None:
        """暂停（停在当前帧，窗口留在原地）。"""
        self._submit(CTRL_PAUSE)

    def quit(self) -> None:
        """关闭窗口并结束舞者线程。"""
        self._submit(CTRL_QUIT)

    def reload(self, gif_path: str) -> None:
        """热更换 GIF 素材（窗口开着则原地换装，未开则下次启动生效）。"""
        self._gif_path = gif_path
        if self.is_alive:
            self._cmd_queue.put(CTRL_RELOAD)

    @property
    def gif_path(self) -> str:
        return self._gif_path

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _submit(self, cmd: str) -> None:
        self._ensure_thread()
        self._cmd_queue.put(cmd)

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._run,
                name='bangboo-dancer',
                daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        try:
            from .dancer_window import DancerWindow

            DancerWindow(
                self._gif_path,
                self._cmd_queue,
                get_gif_path=lambda: self._gif_path,
            ).run()
        except Exception:
            log.error('邦布舞者线程异常退出', exc_info=True)


# 模块级单例：工厂热刷新重复实例化时，所有回调都落到同一个控制器上，天然幂等
_controller: DancerController | None = None
_controller_lock = threading.Lock()


def get_dancer_controller(gif_path: str) -> DancerController:
    global _controller
    if _controller is None:
        with _controller_lock:
            if _controller is None:
                _controller = DancerController(gif_path)
    return _controller
