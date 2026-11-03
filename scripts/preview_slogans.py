# -*- coding: utf-8 -*-
"""Slogan 候选预览：复用 make_cover 逻辑，4 条各渲染一版拼图。"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
W, H = 600, 376
PLUGIN_DIR = Path(__file__).parent.parent
FONT_CN = r'C:\Windows\Fonts\msyhbd.ttc'
FONT_EN = r'C:\Windows\Fonts\bahnschrift.ttf'

CANDIDATES = [
    '哒哒哒～开工咯，跟邦布蹦蹦跳！',
    '邦布上岗！跳舞给你加油哒',
    '一条龙开工，邦布贴贴跳舞',
    '干活哒日子，也要蹦蹦跳跳！',
]


def build(slogan: str) -> Image.Image:
    bg = Image.new('RGB', (W, H), (24, 28, 44))
    glow = Image.new('RGB', (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W - 320, -120, W + 80, 260], fill=(255, 140, 60))
    gd.ellipse([-140, H - 200, 180, H + 120], fill=(70, 90, 200))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    bg = Image.blend(bg, Image.composite(glow, bg, Image.new('L', (W, H), 110)), 0.85)

    grad = Image.new('L', (1, H))
    for y in range(H):
        t = max(0.0, (y / H - 0.62) / 0.38)
        grad.putpixel((0, y), int(200 * t))
    grad = grad.resize((W, H))
    dark = Image.new('RGB', (W, H), (0, 0, 0))
    bg = Image.composite(dark, bg, grad)

    gif = Image.open(PLUGIN_DIR / 'bangboo_companion' / 'assets' / 'dance.gif')
    gif.seek(2)
    art = gif.convert('RGBA')
    target_h = 340
    scale = target_h / art.height
    art = art.resize((int(art.width * scale), target_h), Image.Resampling.LANCZOS)
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

    d = ImageDraw.Draw(bg)
    f_title = ImageFont.truetype(FONT_CN, 58)
    f_sub = ImageFont.truetype(FONT_CN, 22)
    f_en = ImageFont.truetype(FONT_EN, 18)
    f_tag = ImageFont.truetype(FONT_CN, 26)
    d.text((36, 52), '邦布伴侣', font=f_title, fill=(255, 244, 230))
    d.text((40, 128), slogan, font=f_sub, fill=(255, 190, 130))
    d.text((40, 164), 'BANGBOO COMPANION', font=f_en, fill=(150, 160, 190))
    return bg.convert('RGB')


def main():
    pad, label_h = 14, 44
    out_w = 560
    scale = out_w / W
    out_h = (H * scale + label_h + pad) * len(CANDIDATES) + pad
    sheet = Image.new('RGB', (out_w + pad * 2, int(out_h)), (16, 18, 28))
    d = ImageDraw.Draw(sheet)
    f_label = ImageFont.truetype(FONT_CN, 24)
    for i, slogan in enumerate(CANDIDATES):
        y = int(i * (H * scale + label_h + pad) + pad)
        d.text((pad + 4, y), f'候选 {i + 1}: {slogan}', font=f_label, fill=(240, 240, 240))
        cover = build(slogan).resize((out_w, int(H * scale)), Image.Resampling.LANCZOS)
        sheet.paste(cover, (pad, y + label_h))
    out = Path(__file__).parent.parent / 'slogan_preview.png'
    sheet.save(out, quality=92)
    print('preview saved:', out)


if __name__ == '__main__':
    main()
