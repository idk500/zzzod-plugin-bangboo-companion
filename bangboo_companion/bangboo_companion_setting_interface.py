"""邦布伴侣设置页：自定义 GIF 素材。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QWidget
from qfluentwidgets import FluentIcon, InfoBar, InfoBarPosition

from one_dragon.utils.i18_utils import gt
from one_dragon_qt.widgets.column import Column
from one_dragon_qt.widgets.setting_card.push_setting_card import PushSettingCard
from one_dragon_qt.widgets.setting_card.text_setting_card import TextSettingCard
from one_dragon_qt.widgets.vertical_scroll_interface import VerticalScrollInterface

from . import bangboo_companion_const
from .bangboo_companion_config import BangbooCompanionConfig
from .bangboo_companion_factory import get_default_gif_path
from .dancer import get_dancer_controller

if TYPE_CHECKING:
    from one_dragon.base.operation.one_dragon_context import OneDragonContext


class BangbooCompanionSettingInterface(VerticalScrollInterface):

    def __init__(self, ctx: 'OneDragonContext', parent=None):
        self.ctx: 'OneDragonContext' = ctx

        VerticalScrollInterface.__init__(
            self,
            object_name='bangboo_companion_setting_interface',
            content_widget=None, parent=parent,
            nav_text_cn='邦布伴侣'
        )

    def get_content_widget(self) -> QWidget:
        self.content_widget = Column()

        self.gif_card = TextSettingCard(
            icon=FluentIcon.PHOTO, title=gt('自定义 GIF'),
            content=gt('留空使用内置素材；支持透明背景 GIF，路径或文件名含中文也可'),
            input_placeholder=gt('GIF 文件完整路径'),
        )
        self.gif_card.value_changed.connect(self._on_gip_path_edited)
        self.content_widget.add_widget(self.gif_card)

        self.choose_card = PushSettingCard(
            icon=FluentIcon.FOLDER, title=gt('选择 GIF 文件'),
            content=gt('从电脑里挑一张 GIF 作为邦布的舞蹈素材'),
            text=gt('浏览...'),
        )
        self.choose_card.clicked.connect(self._on_choose_clicked)
        self.content_widget.add_widget(self.choose_card)

        self.reset_card = PushSettingCard(
            icon=FluentIcon.SYNC, title=gt('恢复内置素材'),
            content=gt('清除自定义 GIF，回到插件自带的舞蹈动画'),
            text=gt('恢复默认'),
        )
        self.reset_card.clicked.connect(self._on_reset_clicked)
        self.content_widget.add_widget(self.reset_card)

        return self.content_widget

    def on_interface_shown(self) -> None:
        VerticalScrollInterface.on_interface_shown(self)

        self.config = BangbooCompanionConfig(
            instance_idx=self.ctx.current_instance_idx,
            group_id=bangboo_companion_const.APP_ID,
        )
        self._update_display()

    def _update_display(self) -> None:
        self.gif_card.line_edit.blockSignals(True)
        self.gif_card.line_edit.setText(self.config.gif_path)
        self.gif_card.line_edit.blockSignals(False)

    def _apply(self, gif_path: str) -> None:
        """保存配置并热更换素材。"""
        self.config.gif_path = gif_path
        self._update_display()
        controller = get_dancer_controller(gif_path or get_default_gif_path())
        controller.reload(gif_path or get_default_gif_path())
        InfoBar.success(
            title=gt('已保存'),
            content=gt('邦布已换上新舞蹈') if gif_path else gt('已恢复内置素材'),
            orient=Qt.Orientation.Horizontal, position=InfoBarPosition.TOP,
            duration=2500, parent=self,
        )

    def _on_gip_path_edited(self, new_value: str) -> None:
        self._apply(new_value.strip())

    def _on_choose_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, gt('选择 GIF 素材'), '', gt('GIF 动图 (*.gif);;所有文件 (*.*)'),
        )
        if path:
            self._apply(path)

    def _on_reset_clicked(self) -> None:
        self._apply('')
