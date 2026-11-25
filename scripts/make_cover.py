"""生成运行指示器封面：600x376（市场卡片 300x188 的 2x）。

规范（one_dragon_qt/widgets/plugin_card.py）：KeepAspectRatioByExpanding 居中裁切，
底部 38% 会被压黑渐变，文字放上半部左侧，主体放右侧。
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 600, 376
PLUGIN_DIR = Path(__file__).parent.parent
OUT = PLUGIN_DIR / 'bangboo_companion' / 'assets' / 'ui' / 'cover.png'

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


def build() -> None:
    bg = Image.new('RGB', (W, H), (18, 20, 26))
    bg = _glow(bg, [
        ([W - 260, -140, W + 120, 200], (255, 60, 60)),
        ([W - 220, 180, W + 120, 460], (46, 204, 113)),
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
    d.text((x0, 152), '一条龙跑起来就亮绿，出问题闪红', font=f_sub, fill=(174, 182, 194))
    d.text((x0, 186), '绿 运行中   ·   黄 注意   ·   红 异常', font=f_small, fill=(140, 150, 166))
    d.text((x0, 212), '红灯点一下 = 我知道了', font=f_small, fill=(110, 120, 136))

    cx = 476
    lamps = [
        (86, (255, 59, 59)),
        (156, (255, 176, 32)),
        (226, (46, 204, 113)),
    ]
    r = 40
    for cy, color in lamps:
        halo = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        hd = ImageDraw.Draw(halo)
        hd.ellipse([cx - r - 18, cy - r - 18, cx + r + 18, cy + r + 18], fill=(*color, 90))
        halo = halo.filter(ImageFilter.GaussianBlur(18))
        bg = Image.alpha_composite(bg.convert('RGBA'), halo).convert('RGB')
    d = ImageDraw.Draw(bg, 'RGBA')
    for cy, color in lamps:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*color, 235))

    d.rounded_rectangle([cx - 18, 268, cx + 18, 300], radius=8, fill=(60, 66, 78, 255))
    d.rounded_rectangle([cx - 52, 296, cx + 52, 306], radius=5, fill=(44, 49, 58, 255))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    bg.save(OUT, optimize=True)
    print('cover saved:', OUT, bg.size)


if __name__ == '__main__':
    build()
