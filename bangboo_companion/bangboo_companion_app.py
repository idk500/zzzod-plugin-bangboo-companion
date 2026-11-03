"""邦布伴侣应用：独立运行入口（手动开关舞者，用于测试与把玩）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from one_dragon.base.operation.application_base import Application
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_round_result import OperationRoundResult

from . import bangboo_companion_const
from .dancer import DancerController

if TYPE_CHECKING:
    from one_dragon.base.operation.one_dragon_context import OneDragonContext


class BangbooCompanionApp(Application):
    """手动运行 = 切换跳舞/暂停状态。"""

    def __init__(self, ctx: 'OneDragonContext', controller: DancerController):
        Application.__init__(
            self,
            ctx,
            bangboo_companion_const.APP_ID,
            node_max_retry_times=1,
            need_check_game_win=False,
        )
        self._controller = controller

    @operation_node(name='切换跳舞状态', is_start_node=True, screenshot_before_round=False)
    def toggle_dance(self) -> OperationRoundResult:
        if self._controller.is_alive:
            self._controller.pause()
            return self.round_success('邦布暂停了（再运行一次恢复跳舞）')
        else:
            self._controller.play()
            return self.round_success('邦布开始在桌面跳舞')
