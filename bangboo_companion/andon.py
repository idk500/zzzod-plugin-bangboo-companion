"""安灯（Andon）引擎：把一条龙的运行状态变成远处可读的信号灯。

设计思想（精益安灯三要素）
==========================
1. **状态可视**：绿=运行中、黄=注意（卡死前兆/超时）、红=异常、灰=待机；
2. **异常呼叫**：红灯闪烁 + 声音，直到有人应答（未应答会周期性再提醒）；
3. **应答复位**：左键点击灯牌 = 应答，记录应答时间；异常消除后自动复位。

信号源（全部只读，不干扰一条龙流程）
====================================
- 应用事件总线 ``APPLICATION_START`` / ``APPLICATION_STOP``（带 app_id，即时）
- ``config/<实例>/app_run_record/*.yml`` 的 ``run_status``
  （0=未运行 1=成功 2=失败 3=运行中）——结果判定的权威来源
- ``.debug/monitor/monitor_status.json``：still_streak 连续静止、log_stall_min
  日志停滞、elapsed_min 已运行时长——卡死前兆
- ``.debug/monitor/monitor_result.json``：stuck_frame 等监控击杀结论——事故实锤

线程模型
========
- 引擎对事件回调线程安全：``on_start`` / ``on_stop`` 只写内存与队列；
- 采样 ``sample()`` 与 UI 刷新都在灯牌窗口的 Tk 线程里跑（每 1s 一拍），
  不跨线程碰 Tk 对象；
- 状态变化写 ``plugin_data/bangboo_companion/andon_events.jsonl`` 留痕。
"""

from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from one_dragon.utils import os_utils
from one_dragon.utils.log_utils import log

# 状态
STATE_IDLE = 'idle'
STATE_RUNNING = 'running'
STATE_WARN = 'warn'
STATE_ALARM = 'alarm'

# 链内子应用切换的启停非常密集，STOP 后等一小会儿再回待机，避免灯来回跳
IDLE_DEBOUNCE_SEC = 2.5
# 监控文件超过这个时间没更新就不采信（避免读到几天前的结论）
MONITOR_FRESH_SEC = 180
# 监控结论视为「新事故」的时间窗
MONITOR_RESULT_WINDOW_SEC = 900
# 未应答红灯的声音重提醒间隔
REBEEP_SEC = 60
# 应答后「已应答」红灯的保持时长（过后自动复位，避免一直红着）
ACK_HOLD_SEC = 120


@dataclass
class AndonSnapshot:
    """一次采样得到的灯牌展示数据。"""

    state: str
    title: str
    app_name: str
    elapsed_text: str
    detail: str
    acked: bool
    stats_text: str


class AndonEngine:
    """安灯状态机。模块级单例，供工厂事件回调与灯牌窗口共用。"""

    def __init__(self, ctx):
        self._ctx = ctx
        self._instance_idx: int = int(getattr(ctx, 'current_instance_idx', 1) or 1)
        self._start_ts: float = time.time()

        self._lock = threading.Lock()
        self._running: dict[str, float] = {}
        self._last_stop_ts: float = 0.0
        self._alarm_key: str | None = None
        self._alarm_reason: str = ''
        self._alarm_app: str = ''
        self._alarm_ts: float = 0.0
        self._acked_keys: set[str] = set()
        self._ack_ts: float = 0.0
        self._last_beep_ts: float = 0.0
        self._muted: bool = False

        self._config = None
        self._event_log: Path | None = None
        self._pending_beep: queue.Queue = queue.Queue()

    # ---------- 配置 ----------

    def bind_config(self, config) -> None:
        """绑定配置对象（工厂创建后调用；热刷新时覆盖）。"""
        self._config = config

    def _cfg(self, key: str, default):
        try:
            if self._config is not None:
                return self._config.get(key, default)
        except Exception:
            pass
        return default

    @property
    def muted(self) -> bool:
        return self._muted

    def toggle_mute(self) -> bool:
        self._muted = not self._muted
        return self._muted

    # ---------- 事件入口（任意线程） ----------

    def on_start(self, app_id: str) -> None:
        with self._lock:
            self._running[app_id] = time.time()
            self._last_stop_ts = 0.0
            # 新一轮开始 = 上一轮异常自然复位（安灯：报警已应答且进入新周期）
            if self._alarm_key is not None and self._alarm_key in self._acked_keys:
                self._alarm_key = None
                self._alarm_reason = ''
                self._alarm_app = ''

    def on_stop(self, app_id: str) -> None:
        with self._lock:
            self._running.pop(app_id, None)
            self._last_stop_ts = time.time()

    # ---------- 应答 ----------

    def ack(self) -> bool:
        """应答当前告警（安灯闭环）。返回是否有告警被应答。"""
        with self._lock:
            if self._alarm_key is not None:
                self._acked_keys.add(self._alarm_key)
                self._ack_ts = time.time()
            else:
                return False
            key = self._alarm_key
            app = self._alarm_app
            reason = self._alarm_reason
        acked_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._write_event({
            'ts': acked_at, 'type': 'ack', 'key': key,
            'app': app, 'reason': reason,
        })
        log.info('安灯告警已应答: %s (%s)', reason, app)
        return True

    # ---------- 采样 ----------

    def sample(self) -> AndonSnapshot:
        """采集一次状态，返回灯牌展示数据。在 UI 线程调用。"""
        now = time.time()
        show_names = bool(self._cfg('show_app_name', True))
        records = self._scan_run_records()
        today = datetime.now().strftime('%Y%m%d')

        with self._lock:
            running = {k: v for k, v in self._running.items() if now - v < 8 * 3600}
            last_stop_ts = self._last_stop_ts

        # 运行记录里 run_status=3 的应用也算运行中（GUI 中途启动/事件漏收时兜底）
        for app_id, (st, _dt, _rt, mtime) in records.items():
            if st == 3 and now - mtime < 300:
                running.setdefault(app_id, mtime)

        # ---- 红灯：运行失败 / 监控击杀 ----
        alarm_reason = ''
        alarm_app = ''
        alarm_key = None

        for app_id, (st, dt, _rt, mtime) in records.items():
            if st != 2:
                continue
            if dt != today or mtime < self._start_ts:
                continue
            key = 'fail:%s:%d' % (app_id, int(mtime))
            if key in self._acked_keys:
                continue
            alarm_reason = '%s 运行失败' % self._app_label(app_id)
            alarm_app = app_id
            alarm_key = key
            break

        if alarm_key is None:
            result = self._read_json(self._monitor_dir() / 'monitor_result.json')
            if isinstance(result, dict):
                outcome = str(result.get('outcome') or '')
                ended = str(result.get('ended_at') or '')
                if outcome and outcome != 'ok' and self._recent_iso(ended, MONITOR_RESULT_WINDOW_SEC):
                    key = 'monitor:%s:%s' % (outcome, ended)
                    if key not in self._acked_keys:
                        alarm_key = key
                        alarm_app = 'monitor'
                        alarm_reason = '监控判定异常：%s（已处理 %s 个进程）' % (
                            outcome, (result.get('extra') or {}).get('killed', '?'))

        # 告警源已消失：已应答的再保持一会儿「已应答」红，过后自动复位；
        # 未应答但源没了（记录被清/结论过期）直接复位
        if alarm_key is None and self._alarm_key is not None:
            with self._lock:
                keep = (self._alarm_key in self._acked_keys
                        and now - self._ack_ts < ACK_HOLD_SEC)
                if not keep:
                    self._alarm_key = None
                    self._alarm_reason = ''
                    self._alarm_app = ''

        if alarm_key is not None and alarm_key != self._alarm_key:
            with self._lock:
                self._alarm_key = alarm_key
                self._alarm_reason = alarm_reason
                self._alarm_app = alarm_app
                self._alarm_ts = now
            self._write_event({
                'ts': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'type': 'alarm', 'key': alarm_key,
                'app': alarm_app, 'reason': alarm_reason,
            })
            if not self._muted and bool(self._cfg('sound_enabled', True)):
                self._pending_beep.put(1)

        # ---- 黄灯：监控前兆 / 超时 ----
        warn_reason = ''
        mon_status = self._read_json(self._monitor_dir() / 'monitor_status.json')
        mon_mtime = self._mtime(self._monitor_dir() / 'monitor_status.json')
        if isinstance(mon_status, dict) and mon_mtime and now - mon_mtime < MONITOR_FRESH_SEC:
            if str(mon_status.get('state') or '') == 'running':
                still = int(mon_status.get('still_streak') or 0)
                stall = float(mon_status.get('log_stall_min') or 0)
                elapsed = float(mon_status.get('elapsed_min') or 0)
                if still >= int(self._cfg('warn_still_streak', 6)):
                    warn_reason = '画面连续静止 %d 次采样' % still
                elif stall >= float(self._cfg('warn_log_stall_min', 8)):
                    warn_reason = '日志停滞 %.0f 分钟' % stall
                elif elapsed >= float(self._cfg('app_timeout_min', 45)):
                    warn_reason = '本轮已运行 %.0f 分钟（超阈值）' % elapsed

        # ---- 统计 ----
        ok = sum(1 for st, dt, _r, _m in records.values() if st == 1 and dt == today)
        fail = sum(1 for st, dt, _r, _m in records.values() if st == 2 and dt == today)
        stats_text = '今日 ✓%d ✗%d' % (ok, fail)

        # ---- 状态仲裁：红 > 黄 > 绿 > 灰 ----
        with self._lock:
            alarm_key_now = self._alarm_key
            acked = alarm_key_now is not None and alarm_key_now in self._acked_keys
            alarm_reason_now = self._alarm_reason
            alarm_app_now = self._alarm_app

        if alarm_key_now is not None and not acked:
            if not self._muted and bool(self._cfg('sound_enabled', True)):
                if now - self._last_beep_ts >= REBEEP_SEC:
                    self._last_beep_ts = now
                    self._pending_beep.put(1)
            return AndonSnapshot(
                state=STATE_ALARM, title='异常', app_name=alarm_reason_now,
                elapsed_text=self._elapsed_alarm(),
                detail='左键点击应答', acked=False, stats_text=stats_text,
            )

        if acked:
            return AndonSnapshot(
                state=STATE_ALARM, title='异常·已应答', app_name=alarm_reason_now,
                elapsed_text=self._elapsed_alarm(),
                detail='等待下一轮恢复', acked=True, stats_text=stats_text,
            )

        if warn_reason:
            return AndonSnapshot(
                state=STATE_WARN, title='注意',
                app_name=self._current_app_label(running, show_names),
                elapsed_text=self._elapsed_running(running),
                detail=warn_reason, acked=False, stats_text=stats_text,
            )

        if running or (now - last_stop_ts < IDLE_DEBOUNCE_SEC and last_stop_ts > 0):
            return AndonSnapshot(
                state=STATE_RUNNING, title='运行中',
                app_name=self._current_app_label(running, show_names),
                elapsed_text=self._elapsed_running(running),
                detail='点击灯牌可查看应答状态', acked=False, stats_text=stats_text,
            )

        return AndonSnapshot(
            state=STATE_IDLE, title='待机', app_name='无应用运行',
            elapsed_text='', detail='等待一条龙启动', acked=False, stats_text=stats_text,
        )

    def pop_beep(self) -> bool:
        """UI 线程取一次蜂鸣请求。"""
        try:
            self._pending_beep.get_nowait()
            return True
        except queue.Empty:
            return False

    # ---------- 内部 ----------

    def _app_label(self, app_id: str) -> str:
        try:
            info = self._ctx.factory_manager.get_plugin_info(app_id)
            if info is not None and info.app_name:
                return info.app_name
        except Exception:
            pass
        return app_id

    def _current_app_label(self, running: dict[str, float], show_names: bool) -> str:
        if not running:
            return ''
        app_id = max(running.items(), key=lambda kv: kv[1])[0]
        if app_id == 'monitor':
            return '监控'
        return self._app_label(app_id) if show_names else app_id

    @staticmethod
    def _elapsed_running(running: dict[str, float]) -> str:
        if not running:
            return ''
        started = min(running.values())
        sec = max(0, int(time.time() - started))
        m, s = divmod(sec, 60)
        if m >= 60:
            h, m = divmod(m, 60)
            return '%d:%02d:%02d' % (h, m, s)
        return '%02d:%02d' % (m, s)

    def _elapsed_alarm(self) -> str:
        with self._lock:
            ts = self._alarm_ts
        if not ts:
            return ''
        m = int((time.time() - ts) / 60)
        return '%d 分钟前报警' % m if m > 0 else '刚刚报警'

    def _run_record_dir(self) -> Path:
        return Path(os_utils.get_path_under_work_dir(
            'config', '%02d' % self._instance_idx, 'app_run_record'))

    def _monitor_dir(self) -> Path:
        return Path(os_utils.get_path_under_work_dir('.debug', 'monitor'))

    def _scan_run_records(self) -> dict[str, tuple[int, str, str, float]]:
        out: dict[str, tuple[int, str, str, float]] = {}
        d = self._run_record_dir()
        if not d.is_dir():
            return out
        for p in d.glob('*.yml'):
            if '.bak' in p.name:
                continue
            try:
                text = p.read_text(encoding='utf-8')
                data = _loads_yaml_like(text)
                st = data.get('run_status', 0)
                if not isinstance(st, int):
                    continue
                out[p.stem] = (
                    st, str(data.get('dt', '')), str(data.get('run_time', '')), p.stat().st_mtime,
                )
            except Exception:
                continue
        return out

    @staticmethod
    def _read_json(p: Path):
        try:
            if not p.is_file():
                return None
            return json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            return None

    @staticmethod
    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime if p.is_file() else 0.0
        except OSError:
            return 0.0

    @staticmethod
    def _recent_iso(text: str, window_sec: float) -> bool:
        if not text:
            return False
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
            try:
                dt = datetime.strptime(text[:19], fmt)
                return (datetime.now() - dt).total_seconds() <= window_sec
            except ValueError:
                continue
        return False

    def _write_event(self, item: dict) -> None:
        try:
            if self._event_log is None:
                base = self._ctx.get_plugin_data_dir('bangboo_companion')
                self._event_log = Path(base) / 'andon_events.jsonl'
            with self._event_log.open('a', encoding='utf-8') as f:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        except Exception:
            log.debug('安灯事件写入失败', exc_info=True)


def _loads_yaml_like(text: str) -> dict:
    """轻量 YAML 读取：优先 pyyaml，缺失时退化为逐行 key: value 解析。

    运行记录只用到 run_status/dt/run_time 三个标量字段，退化解析足够。
    """
    try:
        import yaml
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        out: dict = {}
        for line in text.splitlines():
            if ':' not in line or line.lstrip().startswith('#'):
                continue
            k, v = line.split(':', 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if not k:
                continue
            try:
                out[k] = int(v)
            except ValueError:
                out[k] = v
        return out


# ---------- 模块级单例 ----------

_engine: AndonEngine | None = None
_engine_lock = threading.Lock()


def get_andon_engine(ctx) -> AndonEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = AndonEngine(ctx)
    return _engine
