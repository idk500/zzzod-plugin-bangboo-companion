"""舞者窗口：Tk 透明置顶无边框窗口 + GIF 逐帧播放。

必须在舞者线程内使用（Tk 对象与线程绑定）。
"""

from __future__ import annotations

import queue

from PIL import Image, ImageTk, ImageSequence
from PIL.Image import Resampling
import tkinter as tk

from one_dragon.utils.log_utils import log

from .dancer import CTRL_PAUSE, CTRL_PLAY, CTRL_QUIT, CTRL_RELOAD, KEY_COLOR

_KEY_COLOR_HEX = '#%02x%02x%02x' % KEY_COLOR
_KEY_COLOR_RGB = KEY_COLOR


def _load_frames(gif_path: str) -> tuple[list[Image.Image], list[int], int, int]:
    """加载 GIF 全部帧（纯 PIL，无 Tk 依赖），透明像素合成到抠色底上。

    Returns:
        (frames, delays_ms, width, height)
    """
    with Image.open(gif_path) as im:
        frames: list[Image.Image] = []
        delays: list[int] = []
        for frame in ImageSequence.Iterator(im):
            rgba = frame.convert('RGBA')
            # 缩放到合适桌面尺寸：高约 220px
            target_h = 220
            if rgba.height > target_h:
                scale = target_h / rgba.height
                rgba = rgba.resize(
                    (max(1, int(rgba.width * scale)), target_h),
                    Resampling.LANCZOS,
                )
            bg = Image.new('RGBA', rgba.size, (*_KEY_COLOR_RGB, 255))
            bg.alpha_composite(rgba)
            frames.append(bg.convert('RGB'))
            delays.append(int(frame.info.get('duration', 50)) or 50)
        width, height = frames[0].size
        return frames, delays, width, height


class DancerWindow:
    """桌面舞者窗口。"""

    def __init__(self, gif_path: str, cmd_queue: queue.Queue, get_gif_path=None):
        self._cmd_queue = cmd_queue
        self._get_gif_path = get_gif_path or (lambda: gif_path)
        self._playing = True

        self._root = tk.Tk()
        self._root.title('bangboo-dancer')
        self._root.overrideredirect(True)
        self._root.attributes('-topmost', True)
        self._root.attributes('-transparentcolor', _KEY_COLOR_HEX)

        self._pil_frames, self._delays, w, h = _load_frames(gif_path)

        self._canvas = tk.Canvas(
            self._root, width=w, height=h,
            bg=_KEY_COLOR_HEX, highlightthickness=0, bd=0,
        )
        self._canvas.pack()
        # Tk 建好后才能转 PhotoImage
        self._frames = [ImageTk.PhotoImage(f, master=self._root) for f in self._pil_frames]
        self._photo_ids = [
            self._canvas.create_image(0, 0, image=f, anchor='nw')
            for f in self._frames
        ]
        for pid in self._photo_ids[1:]:
            self._canvas.itemconfigure(pid, state='hidden')

        # 初始位置：屏幕右下角、任务栏上方
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        self._root.geometry(f'+{sw - w - 40}+{sh - h - 80}')

        self._frame_idx = 0
        self._after_id: str | None = None
        self._bind_mouse()
        self._schedule_next(0)

    # ---------- 播放控制 ----------

    def _schedule_next(self, delay_ms: int) -> None:
        if self._after_id is not None:
            try:
                self._root.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = self._root.after(delay_ms, self._tick)

    def _tick(self) -> None:
        if self._playing and len(self._frames) > 1:
            self._canvas.itemconfigure(self._photo_ids[self._frame_idx], state='hidden')
            self._frame_idx = (self._frame_idx + 1) % len(self._frames)
            self._canvas.itemconfigure(self._photo_ids[self._frame_idx], state='normal')
        delay = self._delays[self._frame_idx]
        self._after_id = self._root.after(delay, self._tick)

    def _reload_frames(self, gif_path: str) -> None:
        """热更换素材：重建全部帧与画布元素，保持窗口位置。"""
        try:
            pil_frames, delays, w, h = _load_frames(gif_path)
        except Exception:
            log.error('邦布 GIF 更换失败: %s', gif_path, exc_info=True)
            return
        for pid in self._photo_ids:
            self._canvas.delete(pid)
        self._canvas.configure(width=w, height=h)
        self._pil_frames = pil_frames
        self._delays = delays
        self._frames = [ImageTk.PhotoImage(f, master=self._root) for f in pil_frames]
        self._photo_ids = [
            self._canvas.create_image(0, 0, image=f, anchor='nw')
            for f in self._frames
        ]
        for pid in self._photo_ids[1:]:
            self._canvas.itemconfigure(pid, state='hidden')
        self._frame_idx = 0
        log.info('邦布 GIF 已更换: %s', gif_path)

    # ---------- 鼠标交互 ----------

    def _bind_mouse(self) -> None:
        self._dragging = False
        self._dx = 0
        self._dy = 0
        self._canvas.bind('<ButtonPress-1>', self._on_press)
        self._canvas.bind('<B1-Motion>', self._on_drag)

        menu = tk.Menu(self._root, tearoff=0)
        menu.add_command(label='暂停/播放', command=self._toggle)
        menu.add_separator()
        menu.add_command(label='退出', command=self._do_quit)
        self._menu = menu
        self._canvas.bind('<ButtonPress-3>', lambda e: menu.tk_popup(e.x_root, e.y_root))

    def _on_press(self, event) -> None:
        self._dragging = True
        self._dx = event.x
        self._dy = event.y

    def _on_drag(self, event) -> None:
        if not self._dragging:
            return
        x = self._root.winfo_x() + event.x - self._dx
        y = self._root.winfo_y() + event.y - self._dy
        self._root.geometry(f'+{x}+{y}')

    def _toggle(self) -> None:
        self._playing = not self._playing

    def _do_quit(self) -> None:
        try:
            self._root.destroy()
        except Exception:
            pass

    # ---------- 主循环 ----------

    def run(self) -> None:
        """处理控制指令 + Tk mainloop。线程内独占运行。"""
        self._pump_queue()

        def _on_close() -> None:
            self._root.quit()

        self._root.protocol('WM_DELETE_WINDOW', _on_close)
        self._root.mainloop()
        log.info('邦布舞者窗口已退出')

    def _pump_queue(self) -> None:
        """非阻塞轮询控制队列。"""
        while True:
            try:
                cmd = self._cmd_queue.get_nowait()
            except queue.Empty:
                break
            if cmd == CTRL_PLAY:
                self._playing = True
                log.info('邦布开始跳舞')
            elif cmd == CTRL_PAUSE:
                self._playing = False
                log.info('邦布暂停跳舞')
            elif cmd == CTRL_RELOAD:
                self._reload_frames(self._get_gif_path())
            elif cmd == CTRL_QUIT:
                self._do_quit()
                return
        # 窗口销毁后不再轮询（mainloop 会返回）
        if self._root.winfo_exists():
            self._root.after(200, self._pump_queue)
