"""安灯灯牌窗口：Tk 无边框置顶面板，三色灯柱 + 状态文字。

必须在灯牌线程内使用（Tk 对象与线程绑定）；外部通过 ``AndonPanelController``
的线程安全方法（show/hide/quit）下发指令。

交互
====
- 左键单击：应答当前告警（安灯闭环）
- 左键拖动：移动面板，松手保存坐标
- 右键菜单：应答 / 静音 / 隐藏 / 退出
"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import font as tkfont

from one_dragon.utils.log_utils import log

from .andon import (
    STATE_ALARM,
    STATE_IDLE,
    STATE_RUNNING,
    STATE_WARN,
    AndonEngine,
)

# 控制指令
CTRL_SHOW = 'show'
CTRL_HIDE = 'hide'
CTRL_QUIT = 'quit'
CTRL_RESET_POS = 'reset_pos'

BG = '#14161a'
BG_EDGE = '#2b3038'
FG_TITLE = '#f2f4f8'
FG_SUB = '#aeb6c2'
FG_DIM = '#6b7280'

LAMP_RED = '#ff3b3b'
LAMP_RED_DIM = '#3a1518'
LAMP_AMBER = '#ffb020'
LAMP_AMBER_DIM = '#3a2a10'
LAMP_GREEN = '#2ecc71'
LAMP_GREEN_DIM = '#123527'

WIDTH = 176
LAMP_AREA_H = 196
HEIGHT = 330

BLINK_MS = 450


class AndonWindow:
    """安灯灯牌主窗口。"""

    def __init__(self, engine: AndonEngine, cmd_queue: queue.Queue, load_pos, save_pos):
        self._engine = engine
        self._cmd_queue = cmd_queue
        self._load_pos = load_pos
        self._save_pos = save_pos

        self._root = tk.Tk()
        self._root.title('bangboo-andon')
        self._root.overrideredirect(True)
        self._root.attributes('-topmost', True)
        self._root.configure(bg=BG_EDGE)

        self._blink_on = True
        self._last_state = None
        self._dragging = False
        self._drag_moved = False

        self._build_ui()
        self._place_window()
        self._bind_mouse()
        self._tick()
        self._pump_queue()

    # ---------- 界面 ----------

    def _build_ui(self) -> None:
        self._body = tk.Frame(self._root, bg=BG, bd=0, highlightthickness=0)
        self._body.pack(fill='both', expand=True, padx=2, pady=2)

        self._canvas = tk.Canvas(
            self._body, width=WIDTH, height=LAMP_AREA_H,
            bg=BG, highlightthickness=0, bd=0,
        )
        self._canvas.pack()

        r = 25
        cx = WIDTH // 2
        self._lamp_red = self._canvas.create_oval(
            cx - r, 40 - r, cx + r, 40 + r, fill=LAMP_RED_DIM, outline='')
        self._lamp_amber = self._canvas.create_oval(
            cx - r, 104 - r, cx + r, 104 + r, fill=LAMP_AMBER_DIM, outline='')
        self._lamp_green = self._canvas.create_oval(
            cx - r, 168 - r, cx + r, 168 + r, fill=LAMP_GREEN_DIM, outline='')
        # 灯之间的小刻度线，呼应工业灯柱
        for y in (72, 136):
            self._canvas.create_line(cx - 14, y, cx + 14, y, fill='#2b3038', width=2)

        base = tkfont.nametofont('TkDefaultFont').copy()
        base.configure(family='Microsoft YaHei UI', size=9)

        self._title_var = tk.StringVar(value='待机')
        self._title = tk.Label(
            self._body, textvariable=self._title_var, bg=BG, fg=FG_TITLE,
            font=(base.actual('family'), 15, 'bold'), anchor='center',
        )
        self._title.pack(fill='x', pady=(2, 0))

        self._app_var = tk.StringVar(value='无应用运行')
        self._app = tk.Label(
            self._body, textvariable=self._app_var, bg=BG, fg=FG_SUB,
            font=(base.actual('family'), 10), anchor='center',
        )
        self._app.pack(fill='x', pady=(2, 0))

        self._elapsed_var = tk.StringVar(value='')
        self._elapsed = tk.Label(
            self._body, textvariable=self._elapsed_var, bg=BG, fg=FG_DIM,
            font=(base.actual('family'), 9), anchor='center',
        )
        self._elapsed.pack(fill='x')

        self._detail_var = tk.StringVar(value='等待一条龙启动')
        self._detail = tk.Label(
            self._body, textvariable=self._detail_var, bg=BG, fg=FG_SUB,
            font=(base.actual('family'), 9), anchor='center',
            wraplength=WIDTH - 16, justify='center',
        )
        self._detail.pack(fill='x', padx=6, pady=(4, 0))

        self._stats_var = tk.StringVar(value='')
        self._stats = tk.Label(
            self._body, textvariable=self._stats_var, bg=BG, fg=FG_DIM,
            font=(base.actual('family'), 8), anchor='center',
        )
        self._stats.pack(side='bottom', fill='x', pady=(0, 4))

    def _place_window(self) -> None:
        pos = self._load_pos() if self._load_pos else (-1, -1)
        x, y = (int(pos[0]), int(pos[1])) if pos else (-1, -1)
        self._place_at(x, y)

    def _place_at(self, x: int, y: int) -> None:
        if x < 0 or y < 0:
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()
            x = sw - WIDTH - 32
            y = sh - HEIGHT - 96
        self._root.geometry('%dx%d+%d+%d' % (WIDTH, HEIGHT, x, y))

    def _reposition_default(self) -> None:
        """回到默认位置并落盘（设置页「重置面板位置」用）。"""
        self._place_at(-1, -1)
        if self._save_pos:
            try:
                self._save_pos(self._root.winfo_x(), self._root.winfo_y())
            except Exception:
                log.debug('安灯面板坐标保存失败', exc_info=True)

    # ---------- 鼠标 ----------

    def _bind_mouse(self) -> None:
        for w in (self._body, self._canvas, self._title, self._app,
                  self._elapsed, self._detail, self._stats):
            w.bind('<ButtonPress-1>', self._on_press)
            w.bind('<B1-Motion>', self._on_drag)
            w.bind('<ButtonRelease-1>', self._on_release)
            w.bind('<ButtonPress-3>', self._on_menu)

        menu = tk.Menu(self._root, tearoff=0)
        menu.add_command(label='应答告警', command=self._on_ack)
        menu.add_command(label='静音/取消静音', command=self._on_mute)
        menu.add_separator()
        menu.add_command(label='隐藏面板', command=self._on_hide)
        menu.add_command(label='退出', command=self._on_quit)
        self._menu = menu

    def _on_press(self, event) -> None:
        self._dragging = True
        self._drag_moved = False
        self._dx = event.x_root - self._root.winfo_x()
        self._dy = event.y_root - self._root.winfo_y()
        self._press_xy = (event.x_root, event.y_root)

    def _on_drag(self, event) -> None:
        if not self._dragging:
            return
        px, py = self._press_xy
        if abs(event.x_root - px) + abs(event.y_root - py) > 4:
            self._drag_moved = True
        self._root.geometry('+%d+%d' % (
            event.x_root - self._dx, event.y_root - self._dy,
        ))

    def _on_release(self, event) -> None:
        self._dragging = False
        if self._drag_moved:
            if self._save_pos:
                try:
                    self._save_pos(self._root.winfo_x(), self._root.winfo_y())
                except Exception:
                    log.debug('安灯面板坐标保存失败', exc_info=True)
        else:
            self._on_ack()

    def _on_menu(self, event) -> None:
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def _on_ack(self) -> None:
        if self._engine.ack():
            log.info('安灯：用户已应答告警')
            self._detail_var.set('已应答，等待恢复')

    def _on_mute(self) -> None:
        self._engine.toggle_mute()

    def _on_hide(self) -> None:
        self._root.withdraw()

    def _on_quit(self) -> None:
        try:
            self._root.destroy()
        except Exception:
            pass

    # ---------- 刷新 ----------

    def _tick(self) -> None:
        try:
            snap = self._engine.sample()
        except Exception:
            log.error('安灯采样异常', exc_info=True)
            snap = None

        if snap is not None:
            if snap.state != self._last_state:
                log.info('安灯状态: %s / %s', snap.state, snap.title)
                self._last_state = snap.state
                self._blink_on = True
            self._render(snap)

        if self._engine.pop_beep():
            self._beep()

        self._root.after(500 if self._last_state == STATE_ALARM else 1000, self._tick)

    def _render(self, snap) -> None:
        self._title_var.set(snap.title)
        self._app_var.set(snap.app_name or '')
        self._elapsed_var.set(snap.elapsed_text or '')
        self._detail_var.set(snap.detail or '')
        self._stats_var.set(snap.stats_text or '')

        if snap.state == STATE_ALARM and not snap.acked:
            # 时间相位闪烁：不依赖渲染频率，避免灯牌被多次重绘时相位错乱
            self._blink_on = (int(time.time() * 1000) // BLINK_MS) % 2 == 0
            red = LAMP_RED if self._blink_on else LAMP_RED_DIM
            amber, green = LAMP_AMBER_DIM, LAMP_GREEN_DIM
            self._title.configure(fg=LAMP_RED)
        else:
            red = LAMP_RED if snap.state == STATE_ALARM else LAMP_RED_DIM
            amber = LAMP_AMBER if snap.state == STATE_WARN else LAMP_AMBER_DIM
            green = LAMP_GREEN if snap.state == STATE_RUNNING else LAMP_GREEN_DIM
            self._title.configure(fg=FG_TITLE if snap.state == STATE_IDLE else
                                  (LAMP_AMBER if snap.state == STATE_WARN else FG_TITLE))

        self._canvas.itemconfigure(self._lamp_red, fill=red)
        self._canvas.itemconfigure(self._lamp_amber, fill=amber)
        self._canvas.itemconfigure(self._lamp_green, fill=green)

    def _beep(self) -> None:
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND)
        except Exception:
            pass

    # ---------- 队列与主循环 ----------

    def _pump_queue(self) -> None:
        while True:
            try:
                cmd = self._cmd_queue.get_nowait()
            except queue.Empty:
                break
            if cmd == CTRL_SHOW:
                self._root.deiconify()
                self._root.attributes('-topmost', True)
            elif cmd == CTRL_HIDE:
                self._root.withdraw()
            elif cmd == CTRL_RESET_POS:
                self._reposition_default()
            elif cmd == CTRL_QUIT:
                self._on_quit()
                return
        if self._root.winfo_exists():
            self._root.after(200, self._pump_queue)

    def run(self) -> None:
        self._root.protocol('WM_DELETE_WINDOW', lambda: self._root.quit())
        self._root.mainloop()
        log.info('安灯灯牌窗口已退出')


class AndonPanelController:
    """线程安全的灯牌控制器：懒启动线程、下发 show/hide/quit。"""

    def __init__(self, engine: AndonEngine, load_pos=None, save_pos=None):
        self._engine = engine
        self._cmd_queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._load_pos = load_pos
        self._save_pos = save_pos
        self._visible: bool = False

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def visible(self) -> bool:
        return self._visible

    def show(self) -> None:
        self._ensure_thread()
        self._visible = True
        self._cmd_queue.put(CTRL_SHOW)

    def hide(self) -> None:
        self._visible = False
        if self.is_alive:
            self._cmd_queue.put(CTRL_HIDE)

    def reset_position(self) -> None:
        if self.is_alive:
            self._cmd_queue.put(CTRL_RESET_POS)

    def quit(self) -> None:
        if self.is_alive:
            self._cmd_queue.put(CTRL_QUIT)

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._run, name='bangboo-andon', daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        try:
            AndonWindow(
                self._engine, self._cmd_queue,
                load_pos=self._load_pos, save_pos=self._save_pos,
            ).run()
        except Exception:
            log.error('安灯灯牌线程异常退出', exc_info=True)
