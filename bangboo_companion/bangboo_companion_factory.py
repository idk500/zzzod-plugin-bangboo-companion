from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from one_dragon.base.operation.application.application_config import ApplicationConfig
from one_dragon.base.operation.application.application_factory import ApplicationFactory
from one_dragon.base.operation.application_base import Application, ApplicationEventId

from . import bangboo_companion_const
from .bangboo_companion_app import BangbooCompanionApp
from .bangboo_companion_config import BangbooCompanionConfig
from .dancer import get_dancer_controller

if TYPE_CHECKING:
    from one_dragon.base.operation.one_dragon_context import OneDragonContext


def get_default_gif_path() -> str:
    """内置素材路径（包目录内，部署后随包走）。"""
    return str(Path(__file__).parent / 'assets' / 'dance.gif')


# 模块级注册标记：ctx.init 与手动 refresh 可能多次扫描实例化工厂，
# 监听器只注册一次（回调经模块单例 controller 派发，跨实例幂等）
_listened_ctx_ids: set[int] = set()


class BangbooCompanionAppFactory(ApplicationFactory):
    """邦布伴侣工厂。

    不进一条龙链（DEFAULT_GROUP=False）。工厂在 GUI 启动/插件刷新时实例化，
    借此注册事件监听：任意应用开始运行 → 跳舞；停止运行 → 停帧。
    （一条龙自身不派发 START，详见 _on_app_event 注释）
    """

    def __init__(self, ctx: 'OneDragonContext'):
        ApplicationFactory.__init__(self, bangboo_companion_const)
        self.ctx: 'OneDragonContext' = ctx

        # 自定义素材：config 有配置则用之，否则内置 dance.gif
        custom = self._read_custom_gif()
        self._controller = get_dancer_controller(custom or get_default_gif_path())

        if id(ctx) not in _listened_ctx_ids:
            _listened_ctx_ids.add(id(ctx))
            ctx.listen_event(ApplicationEventId.APPLICATION_START.value, self._on_app_event)
            ctx.listen_event(ApplicationEventId.APPLICATION_STOP.value, self._on_app_event)

    def _read_custom_gif(self) -> str:
        try:
            config = BangbooCompanionConfig(
                instance_idx=self.ctx.current_instance_idx,
                group_id=bangboo_companion_const.APP_ID,
            )
            return config.gif_path or ''
        except Exception:
            return ''

    def apply_custom_gif(self, gif_path: str) -> None:
        """设置页保存后调用：立即热更换素材（空 = 恢复内置）。"""
        self._controller.reload(gif_path or get_default_gif_path())

    def _on_app_event(self, item) -> None:
        # 注意：上游基座 OneDragonApp 覆写 handle_init 且未调用 super()，
        # 一条龙自身不派发「应用开始运行」事件（真实 GUI 日志实证），
        # 因此不能只过滤 data=='one_dragon' 的 START。
        # 放宽口径：任何应用开始 → 跳舞；任何应用停止 → 停帧。
        # 一条龙链内子应用切换时 STOP/START 在舞者 200ms 指令轮询窗口内
        # 顺序消费、净效果=播放，不会闪停；链条真正结束（无后续 START）
        # 才会定格。独立应用跑完同样正确停帧。
        if item.event_id == ApplicationEventId.APPLICATION_START.value:
            self._controller.play()
        else:
            self._controller.pause()

    def create_application(self, instance_idx: int, group_id: str) -> Application:
        return BangbooCompanionApp(self.ctx, self._controller)

    def create_config(
        self, instance_idx: int, group_id: str
    ) -> ApplicationConfig:
        return BangbooCompanionConfig(
            instance_idx=instance_idx,
            group_id=group_id,
        )
