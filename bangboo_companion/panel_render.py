"""运行指示器面板渲染：整块面板一次画成一张 RGBA 图。

为什么整块用 Pillow 画而不用 Tk 控件拼
=====================================
- 尺寸可缩放：按目标像素直接绘制（2~3 倍超采样后缩小），放大缩小都清晰，
  不会出现位图拉伸发糊或控件字号不跟随的问题。
- 视觉统一：圆角、渐变、发光、中文排版都在同一套坐标系里完成。

对外只暴露 :func:`panel_size` 与 :func:`render_panel`，窗口层只负责贴图与事件。
"""

from __future__ import annotations

import os
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

# ---------- 基准尺寸（scale=1.0 时的像素） ----------
BASE_W = 180
BASE_H = 276
ICON_BASE = 132          # 形象区边长（正方形，水平居中）

MIN_SCALE = 0.6
MAX_SCALE = 2.0
SCALE_STEP = 0.1

STATE_IDLE = 'idle'
STATE_RUNNING = 'running'
STATE_WARN = 'warn'
STATE_ALARM = 'alarm'

STATE_COLORS = {
    STATE_IDLE: (110, 119, 132),
    STATE_RUNNING: (52, 211, 121),
    STATE_WARN: (255, 176, 32),
    STATE_ALARM: (255, 69, 69),
}

_BG = (19, 21, 25, 240)
_EDGE = {
    STATE_IDLE: (46, 52, 62, 255),
    STATE_RUNNING: (38, 88, 64, 255),
    STATE_WARN: (138, 104, 40, 255),
    STATE_ALARM: (196, 58, 58, 255),
}

_FONT_BOLD = [r'C:\Windows\Fonts\msyhbd.ttc', r'C:\Windows\Fonts\simhei.ttf']
_FONT_REG = [r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf']
_FONT_LIGHT = [r'C:\Windows\Fonts\msyhl.ttc', r'C:\Windows\Fonts\msyh.ttc']


def clamp_scale(value) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 1.0
    return max(MIN_SCALE, min(MAX_SCALE, round(v, 2)))


def panel_size(scale: float) -> tuple[int, int]:
    """给定缩放比返回面板像素尺寸。"""
    s = clamp_scale(scale)
    return max(110, round(BASE_W * s)), max(170, round(BASE_H * s))


@lru_cache(maxsize=96)
def _font(size: int, weight: str = 'regular'):
    size = max(7, int(size))
    paths = {'bold': _FONT_BOLD, 'regular': _FONT_REG, 'light': _FONT_LIGHT}.get(weight, _FONT_REG)
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


def _rgba(color: tuple[int, int, int], alpha: int = 255) -> tuple[int, int, int, int]:
    return color[0], color[1], color[2], max(0, min(255, int(alpha)))


def _shade(color: tuple[int, int, int], k: float) -> tuple[int, int, int]:
    return int(color[0] * k), int(color[1] * k), int(color[2] * k)


def _paste_gradient(img: Image.Image, box, radius: int,
                    top: tuple[int, int, int], bottom: tuple[int, int, int]) -> None:
    """圆角 + 竖直渐变填充（Pillow 没有原生渐变圆角矩形）。"""
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    strip = Image.new('RGB', (1, h))
    px = strip.load()
    for j in range(h):
        t = j / max(1, h - 1)
        px[0, j] = tuple(int(round(top[i] + (bottom[i] - top[i]) * t)) for i in range(3))
    grad = strip.resize((w, h), Image.BILINEAR).convert('RGBA')
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, w - 1, h - 1], radius=max(1, min(radius, min(w, h) // 2)), fill=255,
    )
    img.paste(grad, (x0, y0), mask)


def _wrap(text: str, font, max_w: float, max_lines: int = 2) -> list[str]:
    if not text:
        return []
    lines: list[str] = []
    cur = ''
    for ch in text:
        if cur and font.getlength(cur + ch) > max_w:
            lines.append(cur)
            cur = ch
            if len(lines) >= max_lines:
                return lines
        else:
            cur += ch
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines


# ---------------- 形象：Fairy ----------------

def _draw_fairy(img: Image.Image, d: ImageDraw.ImageDraw, box, state: str,
                blink_on: bool, us: float) -> None:
    """悬浮小机器人（方块头 + 屏幕脸 + 天线 + 状态光晕）。

    状态体现在三处：眼睛形状、天线/底座光晕颜色、屏幕亮度。
    """
    x0, y0, size = box
    u = size / 100.0
    base = STATE_COLORS.get(state, STATE_COLORS[STATE_IDLE])
    idle = state == STATE_IDLE
    lit = 1.0 if (state != STATE_ALARM or blink_on) else 0.4

    def X(v: float) -> float:
        return x0 + v * u

    def Y(v: float) -> float:
        return y0 + v * u

    def px(v: float) -> float:
        return v * u

    def col(c: tuple[int, int, int], a: int = 255, k: float = 1.0):
        return _rgba(_shade(c, k * lit), a)

    # 底座光晕（悬浮感）：三层椭圆，越外越淡
    if not idle:
        for rmul, alpha in ((1.0, 26), (0.74, 46), (0.5, 78)):
            bw, bh = px(33) * rmul, px(12) * rmul
            d.ellipse([X(50) - bw, Y(85) - bh, X(50) + bw, Y(85) + bh], fill=col(base, alpha))

    # 地面投影
    d.ellipse([X(38), Y(89), X(62), Y(93)], fill=(0, 0, 0, 96))

    # 天线（先画杆，球后画压在上面）
    d.line([X(50), Y(15), X(50), Y(23)], fill=(148, 158, 173, 255), width=max(1, round(px(2.2))))
    if not idle:
        d.ellipse([X(50) - px(8), Y(10) - px(8), X(50) + px(8), Y(10) + px(8)], fill=col(base, 34))
    d.ellipse([X(50) - px(4.2), Y(10) - px(4.2), X(50) + px(4.2), Y(10) + px(4.2)],
              fill=col(base, 255) if not idle else _rgba(_shade(base, 0.9)))
    d.ellipse([X(50) - px(1.8), Y(10) - px(2.4), X(50) + px(0.4), Y(10) - px(0.2)],
              fill=(255, 255, 255, 190 if not idle else 90))

    # 两侧悬浮小手
    for hx in (19.5, 80.5):
        d.ellipse([X(hx) - px(5.6), Y(45) - px(5.6), X(hx) + px(5.6), Y(45) + px(5.6)],
                  fill=(216, 223, 234, 245), outline=(160, 170, 185, 255),
                  width=max(1, round(px(1.1))))

    # 头部主体（浅色渐变圆角方块）
    _paste_gradient(img, [X(25), Y(19), X(75), Y(67)], int(round(px(13))),
                    (246, 249, 253), (203, 212, 224))
    d.rounded_rectangle([X(25), Y(19), X(75), Y(67)], radius=round(px(13)),
                        outline=(146, 157, 173, 255), width=max(1, round(px(1.5))))
    # 顶部高光
    d.rounded_rectangle([X(29), Y(22), X(71), Y(34)], radius=round(px(7)),
                        fill=(255, 255, 255, 90))

    # 屏幕
    d.rounded_rectangle([X(31), Y(29), X(69), Y(61)], radius=round(px(7)),
                        fill=(10, 14, 20, 255), outline=(62, 72, 88, 255),
                        width=max(1, round(px(1.2))))
    # 屏幕反光斜条
    d.line([X(35), Y(57), X(45), Y(33)], fill=(255, 255, 255, 18), width=max(1, round(px(2.0))))

    eye_l, eye_r, eye_y = 42.0, 58.0, 44.5
    eye = col(base, 255) if not idle else (104, 112, 126, 255)
    if state == STATE_IDLE:
        for ex in (eye_l, eye_r):   # 闭眼：短横线
            d.line([X(ex) - px(4.6), Y(eye_y), X(ex) + px(4.6), Y(eye_y)], fill=eye,
                   width=max(1, round(px(2.4))))
        mouth = None
    elif state == STATE_RUNNING:
        for ex in (eye_l, eye_r):   # 笑眼：上弯弧
            d.arc([X(ex) - px(6), Y(eye_y) - px(5.5), X(ex) + px(6), Y(eye_y) + px(4.5)],
                  200, 340, fill=eye, width=max(2, round(px(2.6))))
        mouth = 'smile'
    elif state == STATE_WARN:
        for ex in (eye_l, eye_r):   # 竖椭圆：注意
            d.ellipse([X(ex) - px(2.8), Y(eye_y) - px(5.4), X(ex) + px(2.8), Y(eye_y) + px(5.4)],
                      fill=eye)
        mouth = 'flat'
        # 屏幕右上角的感叹号
        d.rounded_rectangle([X(62.5), Y(33.5), X(66.5), Y(41.5)], radius=round(px(1.6)),
                            fill=col(base, 255))
        d.ellipse([X(62.8), Y(43.0), X(66.2), Y(46.4)], fill=col(base, 255))
    else:
        for ex in (eye_l, eye_r):   # 睁大眼：圆 + 高光
            d.ellipse([X(ex) - px(5.4), Y(eye_y) - px(6.0), X(ex) + px(5.4), Y(eye_y) + px(6.0)],
                      fill=eye)
            d.ellipse([X(ex) - px(4.2), Y(eye_y) - px(4.6), X(ex) - px(1.4), Y(eye_y) - px(1.4)],
                      fill=(255, 255, 255, 210))
        mouth = 'open'

    if mouth == 'smile':
        d.arc([X(45), Y(50), X(55), Y(58)], 20, 160, fill=eye, width=max(1, round(px(2.0))))
    elif mouth == 'flat':
        d.line([X(46), Y(55), X(54), Y(55)], fill=eye, width=max(1, round(px(2.0))))
    elif mouth == 'open':
        d.ellipse([X(47), Y(51), X(53), Y(58)], fill=eye)
        d.ellipse([X(48), Y(52), X(52), Y(56)], fill=(10, 14, 20, 255))


# ---------------- 形象：传统灯柱 ----------------

def _draw_classic(d: ImageDraw.ImageDraw, box, state: str, blink_on: bool, us: float) -> None:
    x0, y0, size = box
    cx = x0 + size / 2
    r = size * 0.138
    gap = size * 0.25
    cy = y0 + size * 0.5
    order = (STATE_ALARM, STATE_WARN, STATE_RUNNING)
    ys = [cy - gap, cy, cy + gap]

    # 灯柱外壳（整体在形象区内垂直居中）
    d.rounded_rectangle(
        [cx - r * 1.45, ys[0] - r * 1.4, cx + r * 1.45, ys[2] + r * 1.4],
        radius=round(r * 0.5), fill=(24, 27, 32, 255), outline=(58, 64, 74, 255),
        width=max(1, round(1.5 * us)),
    )

    for key, y in zip(order, ys):
        c = STATE_COLORS[key]
        on = (state == key)
        if on and key == STATE_ALARM and not blink_on:
            on = False
        if on:
            d.ellipse([cx - r * 1.55, y - r * 1.55, cx + r * 1.55, y + r * 1.55],
                      fill=_rgba(c, 46))
            d.ellipse([cx - r, y - r, cx + r, y + r], fill=_rgba(c))
            d.ellipse([cx - r * 0.62, y - r * 0.62, cx + r * 0.62, y + r * 0.62],
                      fill=(255, 255, 255, 46))
        else:
            d.ellipse([cx - r, y - r, cx + r, y + r], fill=_rgba(_shade(c, 0.22)))
        d.ellipse([cx - r, y - r, cx + r, y + r], outline=(64, 70, 82, 255),
                  width=max(1, round(1.2 * us)))

    # 刻度线
    for i in (0, 1):
        yy = (ys[i] + ys[i + 1]) / 2
        d.line([cx - r * 0.6, yy, cx + r * 0.6, yy], fill=(58, 64, 74, 255),
               width=max(1, round(1.8 * us)))


# ---------------- 整块面板 ----------------

def render_panel(*, scale: float = 1.0, style: str = 'fairy', state: str = STATE_IDLE,
                 title: str = '', app_name: str = '', elapsed: str = '',
                 detail: str = '', stats: str = '', blink_on: bool = True,
                 muted: bool = False) -> Image.Image:
    """渲染整块面板，返回面板尺寸的 RGBA 图。"""
    s = clamp_scale(scale)
    W, H = panel_size(s)
    ss = 2 if W >= 220 else 3
    w, h = W * ss, H * ss
    u = s * ss                       # 1 个「基准像素」对应的绘制像素

    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    edge = _EDGE.get(state, _EDGE[STATE_IDLE])
    if state == STATE_ALARM and not blink_on:
        edge = (120, 44, 44, 255)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=round(15 * u),
                        fill=_BG, outline=edge, width=max(1, round(1.6 * u)))

    icon = round(ICON_BASE * u)
    box = (round((w - icon) / 2), round(7 * u), icon)
    if style == 'classic':
        _draw_classic(d, box, state, blink_on, u)
    else:
        _draw_fairy(img, d, box, state, blink_on, u)

    cx = w / 2
    base = STATE_COLORS.get(state, STATE_COLORS[STATE_IDLE])
    lit = blink_on or state != STATE_ALARM

    # 状态标题
    if state == STATE_ALARM:
        title_col = _rgba(_shade((255, 96, 96), 1.0 if lit else 0.55))
    elif state == STATE_WARN:
        title_col = _rgba((255, 190, 76))
    elif state == STATE_RUNNING:
        title_col = _rgba((126, 232, 172))
    else:
        title_col = _rgba((236, 240, 246))
    d.text((cx, round(140 * u)), title or '', font=_font(round(17 * u), 'bold'),
           fill=title_col, anchor='ma')

    # 应用名
    d.text((cx, round(166 * u)), app_name or '',
           font=_font(round(11.5 * u), 'regular'), fill=_rgba((176, 184, 196)), anchor='ma')

    # 耗时
    if elapsed:
        d.text((cx, round(186 * u)), elapsed, font=_font(round(10 * u), 'light'),
               fill=_rgba((124, 132, 146)), anchor='ma')

    # 详情（最多两行）
    if detail:
        f_detail = _font(round(10 * u), 'regular')
        max_w = w - 18 * u
        for i, line in enumerate(_wrap(detail, f_detail, max_w, 2)):
            d.text((cx, round((204 + i * 14.5) * u)), line, font=f_detail,
                   fill=_rgba((156, 164, 176)), anchor='ma')

    # 底部统计
    if stats:
        txt = stats if not muted else stats + '  ·  静音'
        d.text((cx, round(250 * u)), txt, font=_font(round(9 * u), 'light'),
               fill=_rgba((110, 118, 130)), anchor='ma')

    # 极小尺寸时底色描边会显脏，统一按最终尺寸缩一次，顺带抗锯齿
    return img.resize((W, H), Image.LANCZOS)
