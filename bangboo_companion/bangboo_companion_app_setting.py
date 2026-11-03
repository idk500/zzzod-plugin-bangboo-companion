from one_dragon_qt.services.app_setting.app_setting_provider import (
    AppSettingProvider,
    SettingType,
)

from .bangboo_companion_const import APP_ID


class BangbooCompanionAppSetting(AppSettingProvider):
    """邦布伴侣设置入口（自定义 GIF 素材）。"""

    app_id = APP_ID
    setting_type = SettingType.INTERFACE

    @staticmethod
    def get_setting_cls() -> type:
        from .bangboo_companion_setting_interface import (
            BangbooCompanionSettingInterface,
        )

        return BangbooCompanionSettingInterface
