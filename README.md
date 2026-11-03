# zzzod-plugin-bangboo-companion

桌面装饰插件：**一条龙启动时，邦布在桌面右下角跳舞；一条龙停止时定格原地。**

不操作游戏、不占一条龙链位，纯桌面演出。

## 机制

- 插件工厂在 GUI 启动时注册事件监听（`应用开始运行` / `应用停止运行`）
- 只过滤 `one_dragon`（一条龙）事件：开始 → 跳舞，停止 → 暂停留帧
- 舞者是独立 daemon 线程内的 Tk 透明置顶窗口，随 GUI 进程退出

## 使用

- 一条龙照常启动即可，无需把插件加进一条龙列表
- 也可以在「独立应用」里运行「邦布伴侣」手动切换跳舞/暂停
- 左键拖动位置；右键菜单：暂停/播放、退出

## 自定义 GIF

两种方式任选：

1. **设置页**：应用卡片上的「设置」→「自定义 GIF」→ 浏览选择文件（保存后立即热更换，一条龙不用重启）
2. **手动替换**：替换插件目录下 `assets/dance.gif`

支持透明背景 GIF（效果最佳）；`risk` 中的 `filesystem` 即来源于读取你选择的任意路径文件。

## 测试

```bash
# 舞者引擎冒烟测试（含截图）
python scripts/test_dancer.py
# 工厂事件过滤逻辑（mock ctx）
python scripts/test_factory_events.py
# 封面重生成
python scripts/make_cover.py
```

生产环境 E2E（真实 ZContext 扫描链路 + 事件 + 自定义 GIF + 应用运行，不碰游戏）见 OneDragon 侧 `run-e2e-bangboo.py`。
