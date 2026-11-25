"""运行指示器窗口：Tk 无边框置顶面板。

整块面板（背景 + 形象 + 文字）由 :mod:`panel_render` 用 Pillow 画成一张图，
Tk 只负责贴图与鼠标事件 —— 因此缩放时按目标像素重绘，不会发糊。

交互
====
- 左键单击：应答当前告警（安灯闭环）
- 左键拖动：移动面板，松手保存坐标
- 滚轮：缩放面板（60% ~ 200%，步进 10%）
- 右键菜单：应答 / 静音 / 外观（Fairy 形象 · 三色灯柱）/ 大小 / 隐藏 / 退出

所有控件都在灯牌线程内创建，外部只能经 ``AndonPanelController`` 的线程安全方法下发指令。
"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk

from PIL import ImageTk
from one_dragon.utils.log_utils import log

from .andon import (
    STATE_ALARM,
    AndonEngine,
)
from .panel_render import (
    SCALE_STEP,
    clamp_scale,
    panel_size,
    render_panel,
)

# 控制指令
CTRL_SHOW = 'show'
CTRL_HIDE = 'hide'
CTRL_QUIT = 'quit'
CTRL_RESET_POS = 'reset_pos'

BG = '#14161a'

BLINK_MS = 450
STYLE_FAIRY = 'fairy'
STYLE_CLASSIC = 'classic'


class AndonWindow:
    """运行指示器主窗口。"""

    def __init__(self, engine: AndonEngine, cmd_queue: queue.Queue,
                 load_pos=None, save_pos=None,
                 load_scale=None, save_scale=None,
                 load_style=None, save_style=None):
        self._engine = engine
        self._cmd_queue = cmd_queue
        self._load_pos = load_pos
        self._save_pos = save_pos
        self._save_scale = save_scale
        self._save_style = save_style

        try:
            self._scale = clamp_scale(load_scale() if load_scale else 1.0)
        except Exception:
            self._scale = 1.0
        try:
            style = load_style() if load_style else STYLE_FAIRY
        except Exception:
            style = STYLE_FAIRY
        self._style = style if style in (STYLE_FAIRY, STYLE_CLASSIC) else STYLE_FAIRY

        self._w, self._h = panel_size(self._scale)
        self._pos = (0, 0)          # 自己记坐标：geometry 生效前 winfo 会读到旧值
        self._photo = None
        self._img_id: int | None = None
        self._last_key = None
        self._last_state = None

        self._dragging = False
        self._drag_moved = False

        self._root = tk.Tk()
        self._root.title('run-indicator')
        self._root.overrideredirect(True)
        self._root.attributes('-topmost', True)
        self._root.configure(bg=BG)

        self._build_ui()
        self._place_window()
        self._bind_mouse()
        self._tick()
        self._pump_queue()

    # ---------- 界面 ----------

    def _build_ui(self) -> None:
        self._canvas = tk.Canvas(
            self._root, width=self._w, height=self._h,
            bg=BG, highlightthickness=0, bd=0,
        )
        self._canvas.pack(fill='both', expand=True)

    def _place_window(self) -> None:
        pos = None
        if self._load_pos is not None:
            try:
                pos = self._load_pos()
            except Exception:
                pos = None
        x, y = (int(pos[0]), int(pos[1])) if pos else (-1, -1)
        self._place_at(x, y)

    def _place_at(self, x: int, y: int) -> None:
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        # 保存的坐标可能来自已拔掉的副屏或不同尺寸：整块放不下就回默认位置
        if (x < 0 or y < 0
                or x + self._w > sw - 4 or y + self._h > sh - 4):
            x = sw - self._w - 32
            y = sh - self._h - 96
        self._pos = (x, y)
        self._root.geometry('%dx%d+%d+%d' % (self._w, self._h, x, y))

    def _reposition_default(self) -> None:
        """回到默认位置并落盘（设置页「重置灯牌位置」用）。"""
        self._place_at(-1, -1)
        self._save_position()

    def _save_position(self) -> None:
        if self._save_pos:
            try:
                self._save_pos(self._pos[0], self._pos[1])
            except Exception:
                log.debug('运行指示器坐标保存失败', exc_info=True)

    # ---------- 大小与外观 ----------

    def _apply_scale(self, value) -> None:
        new_scale = clamp_scale(value)
        if abs(new_scale - self._scale) < 1e-6:
            return
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        old_x, old_y = self._pos
        old_w, old_h = panel_size(self._scale)
        # 原本贴近右/下边（默认位置就是右下角）时，缩放后继续保持贴边，
        # 否则面板会被屏幕边缘切掉一截
        right_gap = max(0, sw - (old_x + old_w))
        bottom_gap = max(0, sh - (old_y + old_h))

        self._scale = new_scale
        self._w, self._h = panel_size(new_scale)
        self._canvas.configure(width=self._w, height=self._h)

        if right_gap < 48:
            x = sw - self._w - max(0, right_gap)
        else:
            x = old_x + (old_w - self._w) // 2
        if bottom_gap < 100:
            y = sh - self._h - max(0, bottom_gap)
        else:
            y = old_y + (old_h - self._h) // 2
        x = max(0, min(x, max(0, sw - self._w)))
        y = max(0, min(y, max(0, sh - self._h)))
        self._pos = (x, y)
        self._root.geometry('%dx%d+%d+%d' % (self._w, self._h, x, y))

        self._last_key = None
        self._refresh()
        if self._save_scale:
            try:
                self._save_scale(new_scale)
            except Exception:
                log.debug('运行指示器缩放保存失败', exc_info=True)
        if self._save_pos:
            try:
                self._save_pos(x, y)   # 用计算值：geometry 刚设完时 winfo 还是旧值
            except Exception:
                log.debug('运行指示器坐标保存失败', exc_info=True)

    def _set_style(self, style: str) -> None:
        if style not in (STYLE_FAIRY, STYLE_CLASSIC) or style == self._style:
            return
        self._style = style
        try:
            self._style_var.set(style)
        except Exception:
            pass
        self._last_key = None
        self._refresh()
        if self._save_style:
            try:
                self._save_style(style)
            except Exception:
                log.debug('运行指示器外观保存失败', exc_info=True)

    # ---------- 鼠标 ----------

    def _bind_mouse(self) -> None:
        w = self._canvas
        w.bind('<ButtonPress-1>', self._on_press)
        w.bind('<B1-Motion>', self._on_drag)
        w.bind('<ButtonRelease-1>', self._on_release)
        w.bind('<ButtonPress-3>', self._on_menu)
        w.bind('<MouseWheel>', self._on_wheel)
        self._root.bind('<MouseWheel>', self._on_wheel)

        menu = tk.Menu(self._root, tearoff=0)
        menu.add_command(label='应答告警', command=self._on_ack)
        menu.add_command(label='静音/取消静音', command=self._on_mute)
        menu.add_separator()

        self._style_var = tk.StringVar(value=self._style)
        style_menu = tk.Menu(menu, tearoff=0)
        style_menu.add_radiobutton(
            label='Fairy 形象', variable=self._style_var, value=STYLE_FAIRY,
            command=lambda: self._set_style(STYLE_FAIRY),
        )
        style_menu.add_radiobutton(
            label='三色灯柱', variable=self._style_var, value=STYLE_CLASSIC,
            command=lambda: self._set_style(STYLE_CLASSIC),
        )
        menu.add_cascade(label='外观', menu=style_menu)

        menu.add_command(label='放大', command=lambda: self._apply_scale(self._scale + SCALE_STEP))
        menu.add_command(label='缩小', command=lambda: self._apply_scale(self._scale - SCALE_STEP))
        menu.add_command(label='默认大小（100%）', command=lambda: self._apply_scale(1.0))
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
        nx, ny = event.x_root - self._dx, event.y_root - self._dy
        self._pos = (nx, ny)
        self._root.geometry('+%d+%d' % (nx, ny))

    def _on_release(self, event) -> None:
        self._dragging = False
        if self._drag_moved:
            self._save_position()
        else:
            self._on_ack()

    def _on_wheel(self, event) -> str:
        step = SCALE_STEP if event.delta > 0 else -SCALE_STEP
        self._apply_scale(self._scale + step)
        return 'break'

    def _on_menu(self, event) -> None:
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def _on_ack(self) -> None:
        if self._engine.ack():
            log.info('运行指示器：用户已应答告警')
            self._last_key = None
            self._refresh()

    def _on_mute(self) -> None:
        self._engine.toggle_mute()
        self._last_key = None
        self._refresh()

    def _on_hide(self) -> None:
        self._root.withdraw()

    def _on_quit(self) -> None:
        try:
            self._root.destroy()
        except Exception:
            pass

    # ---------- 刷新与绘制 ----------

    def _tick(self) -> None:
        self._refresh()
        self._root.after(500 if self._last_state == STATE_ALARM else 1000, self._tick)

    def _refresh(self) -> None:
        try:
            snap = self._engine.sample()
        except Exception:
            log.error('运行指示器采样异常', exc_info=True)
            snap = None

        if snap is not None:
            if snap.state != self._last_state:
                log.info('运行指示器状态: %s / %s', snap.state, snap.title)
                self._last_state = snap.state
            self._paint(snap)

        if self._engine.pop_beep():
            self._beep()

    def _paint(self, snap) -> None:
        blinking = snap.state == STATE_ALARM and not snap.acked
        # 时间相位闪烁：不依赖渲染频率，多次重绘也不会相位错乱
        blink_on = True
        if blinking:
            blink_on = (int(time.time() * 1000) // BLINK_MS) % 2 == 0

        muted = bool(getattr(self._engine, 'muted', False))
        key = (self._scale, self._style, snap.state, snap.title, snap.app_name,
               snap.elapsed_text, snap.detail, snap.stats_text, blink_on, muted)
        if key == self._last_key:
            return
        self._last_key = key

        try:
            img = render_panel(
                scale=self._scale, style=self._style, state=snap.state,
                title=snap.title, app_name=snap.app_name,
                elapsed=snap.elapsed_text, detail=snap.detail,
                stats=snap.stats_text, blink_on=blink_on, muted=muted,
            )
            self._photo = ImageTk.PhotoImage(img)
        except Exception:
            log.error('运行指示器绘制失败', exc_info=True)
            return

        if self._img_id is None:
            self._img_id = self._canvas.create_image(0, 0, anchor='nw', image=self._photo)
        else:
            self._canvas.itemconfigure(self._img_id, image=self._photo)

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
            try:
                if isinstance(cmd, tuple):
                    kind, value = cmd
                    if kind == 'scale':
                        self._apply_scale(value)
                    elif kind == 'style':
                        self._set_style(value)
                    continue
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
            except Exception:
                log.error('运行指示器指令执行失败: %s', cmd, exc_info=True)

        if self._root.winfo_exists():
            self._root.after(200, self._pump_queue)

    def run(self) -> None:
        self._root.protocol('WM_DELETE_WINDOW', lambda: self._root.quit())
        self._root.mainloop()
        log.info('运行指示器窗口已退出')


class AndonPanelController:
    """线程安全的灯牌控制器：懒启动线程、下发显示/隐藏/缩放/外观指令。"""

    def __init__(self, engine: AndonEngine,
                 load_pos=None, save_pos=None,
                 load_scale=None, save_scale=None,
                 load_style=None, save_style=None):
        self._engine = engine
        self._cmd_queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._load_pos = load_pos
        self._save_pos = save_pos
        self._load_scale = load_scale
        self._save_scale = save_scale
        self._load_style = load_style
        self._save_style = save_style
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

    def set_scale(self, scale: float) -> None:
        """设置面板缩放（0.6~2.0）。窗口未启动时静默丢弃，下次显示时按配置生效。"""
        if self.is_alive:
            self._cmd_queue.put(('scale', clamp_scale(scale)))

    def set_style(self, style: str) -> None:
        if self.is_alive:
            self._cmd_queue.put(('style', style))

    def quit(self) -> None:
        if self.is_alive:
            self._cmd_queue.put(CTRL_QUIT)

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._run, name='bangboo-indicator', daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        try:
            AndonWindow(
                self._engine, self._cmd_queue,
                load_pos=self._load_pos, save_pos=self._save_pos,
                load_scale=self._load_scale, save_scale=self._save_scale,
                load_style=self._load_style, save_style=self._save_style,
            ).run()
        except Exception:
            log.error('运行指示器窗口线程异常退出', exc_info=True)
