"""生成占位 dance.gif：简单像素小人跳舞动画（素材就位前打通链路用）。"""
import os
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("GIF_OUT", REPO / "assets" / "dance.gif"))
if not OUT.parent.is_dir():
    raise SystemExit(f"输出目录不存在：{OUT.parent}，请用环境变量 GIF_OUT 指定路径")

W, H = 160, 220
FRAMES = 8

fig = [(0, -30), (0, -10), (0, -30), (0, -2), (0, -30), (0, -18), (0, -30), (0, -6)]  # 身体上下
arm = [(40, -18), (55, -30), (40, -18), (20, -40), (-20, -18), (-35, -30), (-20, -18), (20, -40)]
leg = [(18, 22), (28, 14), (18, 22), (8, 28), (-18, 22), (-28, 14), (-18, 22), (-8, 28)]

frames = []
for i in range(FRAMES):
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = W // 2, H // 2 + 10
    bx, by = cx + fig[i][0], cy + fig[i][1]
    # 头
    d.ellipse([bx - 22, by - 62, bx + 22, by - 18], fill=(255, 214, 180, 255), outline=(90, 60, 50, 255), width=3)
    # 双马尾
    d.ellipse([bx - 34, by - 52, bx - 18, by - 20], fill=(120, 200, 255, 255))
    d.ellipse([bx + 18, by - 52, bx + 34, by - 20], fill=(120, 200, 255, 255))
    # 头饰
    d.polygon([(bx - 12, by - 66), (bx - 2, by - 78), (bx + 2, by - 62)], fill=(255, 120, 150, 255))
    # 身体
    d.rounded_rectangle([bx - 16, by - 20, bx + 16, by + 26], radius=10, fill=(90, 160, 255, 255))
    # 手
    d.line([bx, by - 10, bx + arm[i][0], by - 10 + arm[i][1] + 10], fill=(255, 214, 180, 255), width=8)
    d.line([bx, by - 10, bx - arm[i][0], by - 10 - arm[i][1] + 10], fill=(255, 214, 180, 255), width=8)
    # 腿
    d.line([bx, by + 26, bx + leg[i][0], by + 26 + leg[i][1]], fill=(60, 70, 120, 255), width=10)
    d.line([bx, by + 26, bx - leg[i][0], by + 26 + leg[i][1]], fill=(60, 70, 120, 255), width=10)
    frames.append(im)

frames[0].save(
    OUT,
    save_all=True, append_images=frames[1:], duration=120, loop=0, transparency=0,
)
print('placeholder gif written:', OUT)
