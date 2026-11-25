from one_dragon_qt.services.app_setting.app_setting_provider import (
    AppSettingProvider,
    SettingType,
)

from .const import APP_ID


class BangbooCompanionAppSetting(AppSettingProvider):
    """运行指示器设置入口。"""

    app_id = APP_ID
    setting_type = SettingType.INTERFACE

    @staticmethod
    def get_setting_cls() -> type:
        from .bangboo_companion_setting_interface import (
            BangbooCompanionSettingInterface,
        )

        return BangbooCompanionSettingInterface
