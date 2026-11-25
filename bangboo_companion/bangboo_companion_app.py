"""运行指示器应用：手动运行 = 显示/隐藏灯牌。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from one_dragon.base.operation.application_base import Application
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_round_result import OperationRoundResult

from . import const

if TYPE_CHECKING:
    from one_dragon.base.operation.one_dragon_context import OneDragonContext

    from .andon_window import AndonPanelController


class BangbooCompanionApp(Application):
    """手动运行 = 显示/隐藏灯牌。"""

    def __init__(self, ctx: 'OneDragonContext', panel: 'AndonPanelController'):
        Application.__init__(
            self,
            ctx,
            const.APP_ID,
            node_max_retry_times=1,
            need_check_game_win=False,
        )
        self._panel = panel

    @operation_node(name='切换灯牌显示', is_start_node=True, screenshot_before_round=False)
    def toggle_panel(self) -> OperationRoundResult:
        if self._panel.visible:
            self._panel.hide()
            return self.round_success('已隐藏，再运行一次恢复显示')
        self._panel.show()
        return self.round_success('已显示')
