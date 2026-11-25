from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from one_dragon.base.operation.application.application_config import ApplicationConfig
from one_dragon.base.operation.application.application_factory import ApplicationFactory
from one_dragon.base.operation.application_base import (
    Application,
    ApplicationEventId,
)

from . import const
from .andon import get_andon_engine
from .andon_window import AndonPanelController
from .bangboo_companion_app import BangbooCompanionApp
from .bangboo_companion_config import BangbooCompanionConfig

if TYPE_CHECKING:
    from one_dragon.base.operation.one_dragon_context import OneDragonContext

# 模块级注册标记：ctx.init 与手动 refresh 可能多次扫描实例化工厂，
# 事件监听只注册一次（回调经模块单例 engine/panel 派发，跨实例幂等）
_listened_ctx_ids: set[int] = set()
_panel_lock = threading.Lock()
_panel: AndonPanelController | None = None


def _get_panel(engine, config: BangbooCompanionConfig | None) -> AndonPanelController:
    """灯牌控制器单例：热刷新不重复起线程。"""
    global _panel
    with _panel_lock:
        if _panel is None:
            def _load_pos():
                if config is None:
                    return (-1, -1)
                return (config.panel_x, config.panel_y)

            def _save_pos(x: int, y: int):
                if config is not None:
                    config.panel_x = x
                    config.panel_y = y

            _panel = AndonPanelController(engine, load_pos=_load_pos, save_pos=_save_pos)
    return _panel


def get_panel_or_none() -> AndonPanelController | None:
    """设置页等外部入口取当前灯牌控制器（未初始化时为 None）。"""
    return _panel


def _is_gui_session() -> bool:
    """当前是否运行在 Qt GUI 会话里（脚本调用不弹窗）。"""
    try:
        from PySide6.QtWidgets import QApplication
        return QApplication.instance() is not None
    except Exception:
        return False


class BangbooCompanionAppFactory(ApplicationFactory):
    """运行指示器工厂。

    不进一条龙链（DEFAULT_GROUP=False）。工厂在 GUI 启动/插件刷新时实例化，
    借此注册应用事件监听：
    - 任意应用开始运行 → 绿灯 + 灯牌亮起
    - 任意应用停止运行 → 交由引擎按运行记录/监控判定状态（失败转红灯）
    （一条龙自身不派发 START，故监听全部应用而非仅链事件）
    """

    def __init__(self, ctx: 'OneDragonContext'):
        ApplicationFactory.__init__(self, const)
        self.ctx: 'OneDragonContext' = ctx

        self._engine = get_andon_engine(ctx)
        self._config = self._read_config()
        if self._config is not None:
            self._engine.bind_config(self._config)
        self._panel = _get_panel(self._engine, self._config)

        if id(ctx) not in _listened_ctx_ids:
            _listened_ctx_ids.add(id(ctx))
            ctx.listen_event(ApplicationEventId.APPLICATION_START.value, self._on_app_event)
            ctx.listen_event(ApplicationEventId.APPLICATION_STOP.value, self._on_app_event)

        # 信号灯是固定装置：装了就一直摆在桌面上（灰=待机），
        # 否则用户跑起来看不到灯，会以为插件没生效。
        # 只在 GUI 会话里自动显示，避免脚本/无界面调用莫名弹出窗口。
        auto_show = self._config.get('auto_show', True) if self._config is not None else True
        if auto_show and _is_gui_session():
            self._panel.show()

    def _read_config(self) -> BangbooCompanionConfig | None:
        try:
            return BangbooCompanionConfig(
                instance_idx=self.ctx.current_instance_idx,
                group_id=const.APP_ID,
            )
        except Exception:
            return None

    @property
    def panel(self) -> AndonPanelController:
        return self._panel

    def _on_app_event(self, item) -> None:
        # 注意：上游基座 OneDragonApp 覆写 handle_init 且未调用 super()，
        # 一条龙自身不派发「应用开始运行」事件，因此监听的是所有应用的启停。
        # 链内切换时 STOP/START 密集到达，引擎按 2.5s 去抖 + run_status 仲裁，
        # 灯不会来回跳。
        app_id = item.data if isinstance(item.data, str) else ''
        if item.event_id == ApplicationEventId.APPLICATION_START.value:
            self._engine.on_start(app_id)
            self._panel.show()
        else:
            self._engine.on_stop(app_id)

    def create_application(self, instance_idx: int, group_id: str) -> Application:
        return BangbooCompanionApp(self.ctx, self._panel)

    def create_config(
        self, instance_idx: int, group_id: str
    ) -> ApplicationConfig:
        return BangbooCompanionConfig(
            instance_idx=instance_idx,
            group_id=group_id,
        )
