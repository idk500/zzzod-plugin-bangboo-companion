"""工厂事件过滤逻辑验证（mock ctx，不起 GUI）。"""
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent.parent
for p in (PLUGIN_DIR, Path(r'/workspace/app/src')):
    sys.path.insert(0, str(p))

from one_dragon.base.operation.application_base import ApplicationEventId

from bangboo_companion.bangboo_companion_factory import BangbooCompanionAppFactory


class FakeBus:
    def __init__(self):
        self.listeners = {}

    def listen_event(self, event_id, cb):
        self.listeners.setdefault(event_id, []).append(cb)


class FakeCtx:
    def __init__(self):
        self.bus = FakeBus()

    def listen_event(self, event_id, cb):
        self.bus.listen_event(event_id, cb)


class FakeItem:
    def __init__(self, event_id, data):
        self.event_id = event_id
        self.data = data


ctx = FakeCtx()
factory = BangbooCompanionAppFactory(ctx)  # type: ignore

# 注册断言
start_id = ApplicationEventId.APPLICATION_START.value
stop_id = ApplicationEventId.APPLICATION_STOP.value
assert len(ctx.bus.listeners[start_id]) == 1, ctx.bus.listeners
assert len(ctx.bus.listeners[stop_id]) == 1

cb = ctx.bus.listeners[start_id][0]
ctrl = factory._controller

# 只响应 one_dragon
cb(FakeItem(start_id, 'inventory_scan'))
assert not ctrl.is_alive, '不应响应其他应用'
cb(FakeItem(start_id, 'one_dragon'))
assert ctrl.is_alive, '一条龙开始应拉起舞者'
import time
time.sleep(0.5)

cb(FakeItem(stop_id, 'one_dragon'))  # 停止不杀窗口只暂停
assert ctrl.is_alive, '停止后窗口应保留（暂停）'
cb(FakeItem(stop_id, 'inventory_scan'))
assert ctrl.is_alive

ctrl.quit()
time.sleep(0.5)
assert not ctrl.is_alive, 'quit 后应退出'
print('ALL PASS: 事件过滤、拉起、暂停保留、退出 全部符合预期')
