# -*- coding: utf-8 -*-
"""安灯引擎离线自测：不依赖 GUI/游戏，用临时目录模拟信号源。

覆盖：
1. 待机（无记录无事件）
2. 事件启动 → 绿灯 + 应用名解析
3. 事件停止 → 去抖窗口内仍为绿灯，之后回待机
4. run_status=2 → 红灯；ack() → 「异常·已应答」且不再重复报警
5. monitor_result.json 击杀结论 → 红灯；ack() 后可复位
6. monitor_status.json still_streak 超阈值 → 黄灯
7. run_status=3（事件漏收）→ 绿灯兜底

用法（在插件仓库根目录）：
    ONEDRAGON_SRC=E:/Z1D/app/src python scripts/test_andon_engine.py
"""
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = os.environ.get('ONEDRAGON_SRC', '')
for p in (str(REPO), SRC):
    if p and p not in sys.path:
        sys.path.insert(0, p)

from bangboo_companion import andon as andon_mod
from bangboo_companion.andon import (
    STATE_ALARM,
    STATE_IDLE,
    STATE_RUNNING,
    STATE_WARN,
    AndonEngine,
)

FAILS = []


def check(name, ok, extra=''):
    print(('PASS ' if ok else 'FAIL ') + name + (('  -> ' + extra) if extra else ''))
    if not ok:
        FAILS.append(name)


class FakeInfo:
    def __init__(self, name):
        self.app_name = name


class FakeFactoryManager:
    def __init__(self, mapping):
        self.mapping = mapping

    def get_plugin_info(self, app_id):
        name = self.mapping.get(app_id)
        return FakeInfo(name) if name else None


class FakeRunContext:
    """模拟 run_context：链本身的运行/暂停/结束状态。"""

    def __init__(self):
        self.is_context_running = False
        self.is_context_pause = False
        self.current_app_id = None
        self.last_run_result = None


class FakeCtx:
    def __init__(self, work: Path):
        self.current_instance_idx = 1
        self.factory_manager = FakeFactoryManager({'coffee': '咖啡店', 'charge_plan': '体力计划'})
        self.run_context = FakeRunContext()
        self._plugin_data = work / 'plugin_data'

    def get_plugin_data_dir(self, app_id):
        d = self._plugin_data / app_id
        d.mkdir(parents=True, exist_ok=True)
        return d


class FakeConfig:
    def __init__(self, data=None):
        self.data = {
            'sound_enabled': False, 'show_app_name': True,
            'warn_still_streak': 6, 'warn_log_stall_min': 8, 'app_timeout_min': 45,
        }
        self.data.update(data or {})

    def get(self, key, default=None):
        return self.data.get(key, default)


def write_record(path: Path, status: int, dt: str, mtime: float):
    path.write_text('run_status: %d\ndt: \'%s\'\nrun_time: 11-25 19:00\n' % (status, dt),
                    encoding='utf-8')
    os.utime(path, (mtime, mtime))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='andon-test-'))
    cfg_dir = tmp / 'config' / '01' / 'app_run_record'
    cfg_dir.mkdir(parents=True)
    mon_dir = tmp / '.debug' / 'monitor'
    mon_dir.mkdir(parents=True)

    # 把引擎的工作目录指向临时目录
    class FakeOsUtils:
        @staticmethod
        def get_path_under_work_dir(*parts):
            return str(tmp.joinpath(*parts))

    andon_mod.os_utils = FakeOsUtils

    ctx = FakeCtx(tmp)
    engine = AndonEngine(ctx)
    engine.bind_config(FakeConfig())

    today = datetime.now().strftime('%Y%m%d')

    # 1. 待机
    snap = engine.sample()
    check('1 待机', snap.state == STATE_IDLE and snap.title == '待机', snap.state)

    # 2. 事件启动
    engine.on_start('coffee')
    snap = engine.sample()
    check('2 绿灯+应用名', snap.state == STATE_RUNNING and snap.app_name == '咖啡店',
          '%s/%s' % (snap.state, snap.app_name))

    # 3. 停止去抖：停止后立即采样仍在运行窗口
    engine.on_stop('coffee')
    snap = engine.sample()
    check('3 停止去抖', snap.state == STATE_RUNNING, snap.state)

    # 4. 运行失败 → 红灯 → 应答
    write_record(cfg_dir / 'coffee.yml', 2, today, time.time() + 1)
    snap = engine.sample()
    check('4a 失败红灯', snap.state == STATE_ALARM and '咖啡店' in snap.app_name,
          '%s/%s' % (snap.state, snap.app_name))
    ok = engine.ack()
    snap = engine.sample()
    check('4b 应答闭环', ok and snap.acked and '已应答' in snap.title,
          '%s/%s' % (snap.acked, snap.title))

    # 5. 监控击杀结论（先清掉失败记录，避免红因覆盖）
    (cfg_dir / 'coffee.yml').unlink()
    (mon_dir / 'monitor_result.json').write_text(
        '{"outcome":"stuck_frame","ended_at":"%s","extra":{"killed":5,"left":0}}'
        % datetime.now().strftime('%Y-%m-%dT%H:%M:%S'), encoding='utf-8')
    snap = engine.sample()
    check('5a 监控击杀红灯', snap.state == STATE_ALARM and '监控' in snap.app_name,
          '%s/%s' % (snap.state, snap.app_name))
    engine.ack()
    snap = engine.sample()
    check('5b 监控告警可应答', snap.acked, str(snap.acked))

    # 6. 监控前兆 → 黄灯
    (mon_dir / 'monitor_status.json').write_text(
        '{"state":"running","elapsed_min":5,"still_streak":9,"log_stall_min":0.5}',
        encoding='utf-8')
    engine.on_start('charge_plan')
    snap = engine.sample()
    check('6 黄灯前兆', snap.state == STATE_WARN and '静止' in snap.detail,
          '%s/%s' % (snap.state, snap.detail))

    # 7. run_status=3 兜底（没有事件也认运行中）
    (mon_dir / 'monitor_status.json').unlink()
    engine.on_stop('charge_plan')
    write_record(cfg_dir / 'charge_plan.yml', 3, today, time.time())
    time.sleep(0.1)
    engine._last_stop_ts = 0.0  # 跳过去抖窗口，验证纯记录判定
    snap = engine.sample()
    check('7 运行记录兜底绿灯', snap.state == STATE_RUNNING and snap.app_name == '体力计划',
          '%s/%s' % (snap.state, snap.app_name))

    # 9. 一条龙整体状态（链本身不派发应用事件，只能轮询）
    (cfg_dir / 'charge_plan.yml').unlink()   # 清掉上一步的运行中记录
    engine._last_stop_ts = 0.0
    rc = ctx.run_context
    rc.is_context_running = True
    rc.current_app_id = 'one_dragon'
    snap = engine.sample()
    check('9 链运行→绿灯', snap.state == STATE_RUNNING and snap.app_name == '一条龙',
          '%s/%s' % (snap.state, snap.app_name))

    rc.is_context_pause = True
    snap = engine.sample()
    check('9b 链暂停→黄灯', snap.state == STATE_WARN and '暂停' in snap.detail,
          '%s/%s' % (snap.state, snap.detail))

    # 10. 链级失败→红灯；手动停止不报红
    class _Result:
        def __init__(self, reason):
            self.finish_reason = reason

    rc.is_context_pause = False
    rc.is_context_running = False
    rc.last_run_result = _Result('FAILED')
    snap = engine.sample()
    check('10 链失败→红灯', snap.state == STATE_ALARM and '失败' in snap.app_name,
          '%s/%s' % (snap.state, snap.app_name))

    engine.ack()
    rc.is_context_running = True
    rc.current_app_id = 'one_dragon'
    snap = engine.sample()
    check('10b 新一轮复位为绿灯', snap.state == STATE_RUNNING, snap.state)

    rc.is_context_running = False
    rc.last_run_result = _Result('STOPPED')
    snap = engine.sample()
    check('10c 手动停止不报警', snap.state != STATE_ALARM, snap.state)

    # 8. 事件日志留痕
    log_path = ctx.get_plugin_data_dir('bangboo_companion') / 'andon_events.jsonl'
    lines = log_path.read_text(encoding='utf-8').strip().splitlines() if log_path.exists() else []
    check('8 事件留痕', len(lines) >= 2, '%d 行' % len(lines))

    print('\n结果: %s' % ('全部通过' if not FAILS else '失败项 %s' % FAILS))
    return 0 if not FAILS else 1


if __name__ == '__main__':
    sys.exit(main())
