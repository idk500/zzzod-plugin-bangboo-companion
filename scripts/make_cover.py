"""生成邦布伴侣封面：600x376（市场卡片 300x188 的 2x）。

规范（one_dragon_qt/widgets/plugin_card.py）：KeepAspectRatioByExpanding 居中裁切，
底部 38% 会被压黑渐变，文字放上半部左侧，主体放右侧。
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 600, 376
PLUGIN_DIR = Path(__file__).parent.parent
OUT = PLUGIN_DIR / 'bangboo_companion' / 'assets' / 'ui' / 'cover.png'

FONT_CN = r'C:\Windows\Fonts\msyhbd.ttc'
FONT_EN = r'C:\Windows\Fonts\bahnschrift.ttf'


def build() -> None:
    # 深色底 + 柔和光斑（邦布橙 + 深蓝夜色）
    bg = Image.new('RGB', (W, H), (24, 28, 44))
    glow = Image.new('RGB', (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W - 320, -120, W + 80, 260], fill=(255, 140, 60))   # 右上橙光
    gd.ellipse([-140, H - 200, 180, H + 120], fill=(70, 90, 200))   # 左下蓝光
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    bg = Image.blend(bg, Image.composite(glow, bg, Image.new('L', (W, H), 110)), 0.85)

    # 底部压暗渐变（模拟市场卡片渲染）
    grad = Image.new('L', (1, H))
    for y in range(H):
        t = max(0.0, (y / H - 0.62) / 0.38)
        grad.putpixel((0, y), int(200 * t))
    grad = grad.resize((W, H))
    dark = Image.new('RGB', (W, H), (0, 0, 0))
    bg = Image.composite(dark, bg, grad)

    # 邦布主体：取 GIF 动感最强的一帧，等比放大
    gif = Image.open(PLUGIN_DIR / 'bangboo_companion' / 'assets' / 'dance.gif')
    gif.seek(2)
    art = gif.convert('RGBA')
    target_h = 340
    scale = target_h / art.height
    art = art.resize((int(art.width * scale), target_h), Image.Resampling.LANCZOS)
    # 描边光晕提升辨识度
    alpha = art.getchannel('A')
    halo = Image.new('RGBA', art.size, (0, 0, 0, 0))
    halo.paste((255, 170, 80, 160), mask=alpha.point(lambda v: 255 if v > 40 else 0))
    halo = halo.filter(ImageFilter.GaussianBlur(6))
    art_rgba = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ax, ay = W - art.width - 28, H - art.height - 12
    art_rgba.alpha_composite(halo, (ax, ay))
    art_rgba.alpha_composite(art, (ax, ay))
    bg = bg.convert('RGBA')
    bg.alpha_composite(art_rgba)

    # 文字：左上
    d = ImageDraw.Draw(bg)
    f_title = ImageFont.truetype(FONT_CN, 58)
    f_sub = ImageFont.truetype(FONT_CN, 22)
    f_en = ImageFont.truetype(FONT_EN, 18)
    d.text((36, 52), '邦布伴侣', font=f_title, fill=(255, 244, 230))
    d.text((40, 128), '一条龙开工，邦布陪你跳舞', font=f_sub, fill=(255, 190, 130))
    d.text((40, 164), 'BANGBOO COMPANION', font=f_en, fill=(150, 160, 190))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    bg.convert('RGB').save(OUT, quality=95)
    print('cover saved:', OUT)


if __name__ == '__main__':
    build()
