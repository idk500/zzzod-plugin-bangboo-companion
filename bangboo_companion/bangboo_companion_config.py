from one_dragon.base.operation.application.application_config import ApplicationConfig

from . import const


class BangbooCompanionConfig(ApplicationConfig):
    """运行指示器配置。"""

    def __init__(self, instance_idx: int, group_id: str):
        ApplicationConfig.__init__(
            self,
            app_id=const.APP_ID,
            instance_idx=instance_idx,
            group_id=group_id,
        )

    # ---------- 面板 ----------

    @property
    def auto_show(self) -> bool:
        """启动程序时自动显示灯牌（关=只在运行时才出现）。"""
        return bool(self.get('auto_show', True))

    @auto_show.setter
    def auto_show(self, new_value: bool) -> None:
        self.update('auto_show', bool(new_value))

    @property
    def panel_x(self) -> int:
        """面板横坐标，-1 = 自动放右下角。"""
        return int(self.get('panel_x', -1) or -1)

    @panel_x.setter
    def panel_x(self, new_value: int) -> None:
        self.update('panel_x', int(new_value))

    @property
    def panel_y(self) -> int:
        """面板纵坐标，-1 = 自动放右下角。"""
        return int(self.get('panel_y', -1) or -1)

    @panel_y.setter
    def panel_y(self, new_value: int) -> None:
        self.update('panel_y', int(new_value))

    def reset_position(self) -> None:
        self.update('panel_x', -1)
        self.update('panel_y', -1)

    @property
    def panel_scale(self) -> float:
        """面板缩放比（0.6~2.0，1.0 = 默认大小）。"""
        try:
            return max(0.6, min(2.0, float(self.get('panel_scale', 1.0) or 1.0)))
        except (TypeError, ValueError):
            return 1.0

    @panel_scale.setter
    def panel_scale(self, new_value) -> None:
        self.update('panel_scale', round(max(0.6, min(2.0, float(new_value))), 2))

    @property
    def panel_style(self) -> str:
        """面板外观：fairy = 悬浮小机器人，classic = 三色灯柱。"""
        value = str(self.get('panel_style', 'fairy') or 'fairy')
        return value if value in ('fairy', 'classic') else 'fairy'

    @panel_style.setter
    def panel_style(self, new_value: str) -> None:
        self.update('panel_style', new_value if new_value in ('fairy', 'classic') else 'fairy')

    @property
    def show_app_name(self) -> bool:
        """文字区显示中文应用名（关则显示 app_id）。"""
        return bool(self.get('show_app_name', True))

    @show_app_name.setter
    def show_app_name(self, new_value: bool) -> None:
        self.update('show_app_name', bool(new_value))

    # ---------- 告警 ----------

    @property
    def sound_enabled(self) -> bool:
        """红灯蜂鸣。"""
        return bool(self.get('sound_enabled', True))

    @sound_enabled.setter
    def sound_enabled(self, new_value: bool) -> None:
        self.update('sound_enabled', bool(new_value))

    # ---------- 黄灯阈值 ----------

    @property
    def warn_still_streak(self) -> int:
        """监控连续静止采样次数达到多少亮黄灯。"""
        return int(self.get('warn_still_streak', 6) or 6)

    @warn_still_streak.setter
    def warn_still_streak(self, new_value: int) -> None:
        self.update('warn_still_streak', int(new_value))

    @property
    def warn_log_stall_min(self) -> float:
        """日志停滞多少分钟亮黄灯。"""
        return float(self.get('warn_log_stall_min', 8) or 8)

    @warn_log_stall_min.setter
    def warn_log_stall_min(self, new_value: float) -> None:
        self.update('warn_log_stall_min', float(new_value))

    @property
    def app_timeout_min(self) -> float:
        """单轮运行多少分钟算超阈值（黄灯）。"""
        return float(self.get('app_timeout_min', 45) or 45)

    @app_timeout_min.setter
    def app_timeout_min(self, new_value: float) -> None:
        self.update('app_timeout_min', float(new_value))
