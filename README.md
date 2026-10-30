# ScreenMng

极简的 Windows 10/11 桌面布局管理工具：一键（或开机时）把指定程序打开到**指定显示器的指定区域**。

例如：副显示器上 Chrome 占上半屏、VS Code 占下半屏，主显示器上 Obsidian 最大化。

- 单个 exe，无需安装，无第三方依赖（纯 Win32 API + tkinter）
- 程序没运行就自动启动，已运行就直接移动窗口
- 支持多显示器、不同缩放比例（100% / 150% / 200% 混用）、竖屏
- 「捕获当前窗口」：先手动摆好，一键存成布局
- 开机自动应用布局

## 下载

到 [Releases](../../releases) 下载 `ScreenMng.exe`，双击运行。配置保存在 `%APPDATA%\ScreenMng\config.json`。

## 使用

1. **新建** 一个布局，点 **添加窗口**：选择程序（exe / 快捷方式），选择显示器和区域。
   不知道哪块屏是几号？点 **识别显示器**（主显示器永远是 1 号，其余从左到右编号）。
2. 或者先把窗口手动摆好，点 **捕获当前窗口…**，勾选要保存的窗口即可。
3. 点 **▶ 应用布局**。
4. 勾选 **开机时自动应用此布局**，登录 Windows 后自动打开并摆好。

右侧预览图会实时显示每个窗口将要占的位置。

### 区域

最大化、铺满、左/右半屏、上/下半屏、四个 1/4 角、左/中/右 1/3、左/右 2/3、上/中/下 1/3、上/下 2/3，
以及 **自定义比例** `x, y, 宽, 高`（占显示器工作区的比例，例如 `0, 0, 0.7, 1` 表示左侧 70%）。

### 同一个程序的多个窗口

给每条规则填 **标题包含**（正则，不区分大小写）来区分，例如两个 Chrome 窗口分别填 `GitHub` 和 `YouTube`。
没填标题时，同一程序的多条规则会依次分配给该程序的不同窗口，窗口不够时自动再启动一个。

## 配置文件

也可以直接编辑 `config.json`（界面里 **打开配置文件**，保存后切回窗口会自动重新加载）：

```json
{
  "layouts": {
    "工作": [
      {"app": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "monitor": 2, "zone": "top"},
      {"app": "%LOCALAPPDATA%\\Programs\\Microsoft VS Code\\Code.exe", "monitor": 2, "zone": "bottom"},
      {"app": "%LOCALAPPDATA%\\Programs\\Obsidian\\Obsidian.exe", "monitor": "primary", "zone": "maximize"}
    ]
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `app` | 要启动的程序：exe 路径、`.lnk` 快捷方式或 URI，支持 `%环境变量%` |
| `args` | 启动参数，可省略 |
| `process` | 用来识别窗口的进程名（如 `Code.exe`），省略时取 `app` 的文件名 |
| `title` | 窗口标题正则，可省略 |
| `monitor` | `"primary"`、`"secondary"`、编号（1 = 主显示器）或设备名 `\\.\DISPLAY2` |
| `zone` | 区域名（`maximize` `full` `left` `right` `top` `bottom` `top-left` `top-right` `bottom-left` `bottom-right` `left-third` `center-third` `right-third` `left-two-thirds` `right-two-thirds` `top-third` `middle-third` `bottom-third` `top-two-thirds` `bottom-two-thirds`）或 `[x, y, 宽, 高]` 比例 |
| `launch` | 窗口不存在时是否启动程序，默认 `true` |

## 命令行

```
ScreenMng.exe                  打开界面
ScreenMng.exe apply 工作        应用布局（--timeout 秒，等待新启动程序窗口，默认 20）
ScreenMng.exe capture 工作      把当前所有窗口保存为布局
ScreenMng.exe list | monitors | windows
```

可以配合任务计划程序、快捷方式或热键工具使用。运行日志在 `%APPDATA%\ScreenMng\screen_mng.log`。

## 限制

- 以管理员身份运行的程序窗口，需要 ScreenMng 也以管理员身份运行才能移动（Windows UIPI 限制）。
- 应用商店（UWP）程序的窗口进程都是 `ApplicationFrameHost.exe`，需要用「标题包含」来识别。

## 从源码运行 / 开发

需要 [uv](https://docs.astral.sh/uv/)：

```
uv sync
uv run screen-mng                # 界面
uv run pytest                    # 测试（含真实窗口的集成测试，会短暂弹出测试窗口）
uv run pyinstaller --noconfirm --onefile --windowed --name ScreenMng src/screen_mng/__main__.py
```

## 实现要点

- 进程设为 Per-Monitor DPI Aware V2，全部使用物理像素坐标。
- 移动窗口前把线程切换到**目标窗口的** DPI 感知方式，避免非 DPI 感知程序在高缩放屏上被系统二次缩放。
- 用 `DWMWA_EXTENDED_FRAME_BOUNDS` 扣除 Win10/11 的透明缩放边框，窗口之间不留缝。
- Chromium / Electron 程序（Chrome、VS Code、Obsidian）启动后会恢复自己记住的位置，启动后会再校正几次。

## License

MIT
