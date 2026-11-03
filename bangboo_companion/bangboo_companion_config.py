from one_dragon.base.operation.application.application_config import ApplicationConfig
from . import bangboo_companion_const


class BangbooCompanionConfig(ApplicationConfig):
    """邦布伴侣配置。"""

    def __init__(self, instance_idx: int, group_id: str):
        ApplicationConfig.__init__(
            self,
            app_id=bangboo_companion_const.APP_ID,
            instance_idx=instance_idx,
            group_id=group_id,
        )

    @property
    def gif_path(self) -> str:
        """自定义 GIF 路径，空 = 使用内置 assets/dance.gif"""
        return self.get('gif_path', '')

    @gif_path.setter
    def gif_path(self, new_value: str) -> None:
        self.update('gif_path', new_value)
