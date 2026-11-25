"""生成运行指示器封面：600x376（市场卡片 300x188 的 2x）。

规范（one_dragon_qt/widgets/plugin_card.py）：KeepAspectRatioByExpanding 居中裁切，
底部 38% 会被压黑渐变，文字放上半部左侧，主体放右侧。
主体直接用插件本体的 Fairy 渲染，保证封面与实际界面一致。
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 600, 376
PLUGIN_DIR = Path(__file__).parent.parent
OUT = PLUGIN_DIR / 'bangboo_companion' / 'assets' / 'ui' / 'cover.png'

sys.path.insert(0, str(PLUGIN_DIR))

FONT_CN = r'C:\Windows\Fonts\msyhbd.ttc'
FONT_CN_REG = r'C:\Windows\Fonts\msyh.ttc'
FONT_EN = r'C:\Windows\Fonts\bahnschrift.ttf'


def _glow(bg, boxes, blur=110, alpha=110):
    glow = Image.new('RGB', (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for box, color in boxes:
        gd.ellipse(box, fill=color)
    glow = glow.filter(ImageFilter.GaussianBlur(blur))
    return Image.blend(bg, Image.composite(glow, bg, Image.new('L', (W, H), alpha)), 0.8)


def _fairy(size: int, state: str) -> Image.Image:
    """用插件本体的绘制函数生成 Fairy 形象（透明底）。"""
    from bangboo_companion.panel_render import _draw_fairy

    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    _draw_fairy(img, ImageDraw.Draw(img), (0, 0, size), state, True, 1.0)
    return img


def build() -> None:
    bg = Image.new('RGB', (W, H), (18, 20, 26))
    bg = _glow(bg, [
        ([W - 300, -120, W + 140, 320], (40, 180, 110)),
        ([W - 200, 220, W + 120, 480], (30, 120, 90)),
        ([-160, H - 220, 200, H + 120], (40, 60, 120)),
    ])

    grad = Image.new('L', (1, H))
    for y in range(H):
        t = max(0.0, (y / H - 0.62) / 0.38)
        grad.putpixel((0, y), int(205 * t))
    grad = grad.resize((W, H))
    bg = Image.composite(Image.new('RGB', (W, H), (0, 0, 0)), bg, grad)

    d = ImageDraw.Draw(bg, 'RGBA')

    f_title = ImageFont.truetype(FONT_CN, 54)
    f_sub = ImageFont.truetype(FONT_CN_REG, 21)
    f_small = ImageFont.truetype(FONT_CN_REG, 16)
    f_en = ImageFont.truetype(FONT_EN, 15)

    x0 = 46
    d.text((x0, 52), '运行指示器', font=f_title, fill=(242, 244, 248))
    d.text((x0 + 3, 122), 'RUN STATUS LIGHT', font=f_en, fill=(120, 132, 150))
    d.text((x0, 152), '一条龙跑起来就亮绿灯', font=f_sub, fill=(174, 182, 194))
    d.text((x0, 186), '绿 运行中   ·   黄 注意   ·   红 异常', font=f_small, fill=(140, 150, 166))
    d.text((x0, 212), '红灯点一下 = 我知道了', font=f_small, fill=(110, 120, 136))

    # 主体：运行中的 Fairy（右侧留白，不压文字）
    fairy = _fairy(300, 'running').resize((238, 238), Image.LANCZOS)
    bg = bg.convert('RGBA')
    bg.alpha_composite(fairy, (W - 262, 54))

    bg.convert('RGB').save(OUT, optimize=True)
    print('cover saved:', OUT, bg.size)


if __name__ == '__main__':
    build()
