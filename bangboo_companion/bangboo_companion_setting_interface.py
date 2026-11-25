"""邦布安灯设置页：告警声音、黄灯阈值、面板位置。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from qfluentwidgets import FluentIcon, InfoBar, InfoBarPosition

from one_dragon.utils.i18_utils import gt
from one_dragon_qt.widgets.column import Column
from one_dragon_qt.widgets.setting_card.push_setting_card import PushSettingCard
from one_dragon_qt.widgets.setting_card.spin_box_setting_card import SpinBoxSettingCard
from one_dragon_qt.widgets.setting_card.switch_setting_card import SwitchSettingCard
from one_dragon_qt.widgets.vertical_scroll_interface import VerticalScrollInterface

from . import const
from .bangboo_companion_config import BangbooCompanionConfig
from .factory import get_panel_or_none

if TYPE_CHECKING:
    from one_dragon.base.operation.one_dragon_context import OneDragonContext


class BangbooCompanionSettingInterface(VerticalScrollInterface):

    def __init__(self, ctx: 'OneDragonContext', parent=None):
        self.ctx: 'OneDragonContext' = ctx

        VerticalScrollInterface.__init__(
            self,
            object_name='bangboo_companion_setting_interface',
            content_widget=None, parent=parent,
            nav_text_cn='邦布安灯'
        )

    def get_content_widget(self) -> QWidget:
        self.content_widget = Column()

        self.sound_card = SwitchSettingCard(
            icon=FluentIcon.SPEAKER, title=gt('红灯蜂鸣'),
            content=gt('出现异常时短鸣提示，未应答会每分钟再提醒一次'),
        )
        self.sound_card.value_changed.connect(self._on_sound_changed)
        self.content_widget.add_widget(self.sound_card)

        self.name_card = SwitchSettingCard(
            icon=FluentIcon.FONT, title=gt('显示中文应用名'),
            content=gt('关闭后文字区显示 app_id（英文标识）'),
        )
        self.name_card.value_changed.connect(self._on_show_name_changed)
        self.content_widget.add_widget(self.name_card)

        self.still_card = SpinBoxSettingCard(
            icon=FluentIcon.STOP_WATCH, title=gt('画面静止阈值'),
            content=gt('监控连续静止采样达到该次数亮黄灯（仅监控脚本运行时生效）'),
            minimum=1, maximum=60,
        )
        self.still_card.value_changed.connect(self._on_still_changed)
        self.content_widget.add_widget(self.still_card)

        self.stall_card = SpinBoxSettingCard(
            icon=FluentIcon.STOP_WATCH, title=gt('日志停滞阈值（分钟）'),
            content=gt('日志超过该时长没有新内容亮黄灯'),
            minimum=1, maximum=120,
        )
        self.stall_card.value_changed.connect(self._on_stall_changed)
        self.content_widget.add_widget(self.stall_card)

        self.timeout_card = SpinBoxSettingCard(
            icon=FluentIcon.STOP_WATCH, title=gt('单轮超时阈值（分钟）'),
            content=gt('一轮运行超过该时长亮黄灯'),
            minimum=10, maximum=240,
        )
        self.timeout_card.value_changed.connect(self._on_timeout_changed)
        self.content_widget.add_widget(self.timeout_card)

        self.reset_card = PushSettingCard(
            icon=FluentIcon.SYNC, title=gt('重置面板位置'),
            content=gt('把灯牌放回屏幕右下角（也可直接拖动灯牌）'),
            text=gt('重置'),
        )
        self.reset_card.clicked.connect(self._on_reset_clicked)
        self.content_widget.add_widget(self.reset_card)

        return self.content_widget

    def on_interface_shown(self) -> None:
        VerticalScrollInterface.on_interface_shown(self)

        self.config = BangbooCompanionConfig(
            instance_idx=self.ctx.current_instance_idx,
            group_id=const.APP_ID,
        )
        self._update_display()

    def _update_display(self) -> None:
        self.sound_card.setValue(self.config.sound_enabled, emit_signal=False)
        self.name_card.setValue(self.config.show_app_name, emit_signal=False)
        self.still_card.setValue(int(self.config.warn_still_streak), emit_signal=False)
        self.stall_card.setValue(int(self.config.warn_log_stall_min), emit_signal=False)
        self.timeout_card.setValue(int(self.config.app_timeout_min), emit_signal=False)

    # ---------- 保存 ----------

    def _on_sound_changed(self, value: bool) -> None:
        self.config.sound_enabled = value

    def _on_show_name_changed(self, value: bool) -> None:
        self.config.show_app_name = value

    def _on_still_changed(self, value) -> None:
        self.config.warn_still_streak = int(value)

    def _on_stall_changed(self, value) -> None:
        self.config.warn_log_stall_min = float(value)

    def _on_timeout_changed(self, value) -> None:
        self.config.app_timeout_min = float(value)

    def _on_reset_clicked(self) -> None:
        self.config.reset_position()
        panel = get_panel_or_none()
        if panel is not None:
            panel.reset_position()
        InfoBar.success(
            title=gt('已重置'),
            content=gt('灯牌已回到屏幕右下角'),
            orient=Qt.Orientation.Horizontal, position=InfoBarPosition.TOP,
            duration=2000, parent=self,
        )
