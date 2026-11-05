"""舞者引擎冒烟测试：play → 截图 → pause → 截图 → quit。"""
import os
import sys
import time
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent.parent
# 一条龙基座源码位置因机器而异，优先读环境变量，其次按安装布局猜
APP_SRC = Path(os.environ.get("ONEDRAGON_SRC", PLUGIN_DIR.parent.parent / "src"))
for p in (PLUGIN_DIR, APP_SRC):
    sys.path.insert(0, str(p))

from PIL import ImageGrab

from bangboo_companion.dancer import get_dancer_controller

gif = PLUGIN_DIR / 'assets' / 'dance.gif'
ctrl = get_dancer_controller(str(gif))

print('--- play ---')
ctrl.play()
time.sleep(3)
print('alive:', ctrl.is_alive)
img1 = ImageGrab.grab(bbox=None)
img1.save(str(PLUGIN_DIR / '.debug_play.png'))
print('screenshot play saved')

print('--- pause ---')
ctrl.pause()
time.sleep(1)
img2 = ImageGrab.grab(bbox=None)
img2.save(str(PLUGIN_DIR / '.debug_pause.png'))

print('--- quit ---')
ctrl.quit()
time.sleep(1)
print('alive after quit:', ctrl.is_alive)
print('DONE')
