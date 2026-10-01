# GhostValue

Windows 单机游戏修改器实验项目，当前适配 **Kingdom Rush Genesis**（本地已验证版本 1.00.052 / Steam build 25534662）。使用 Python 标准库和 Tkinter，无运行时第三方依赖。

## 功能

- 自动定位局内金币，无需数值筛选，也无需暂停；默认目标金额为 **50000**。
- 英雄、防御塔和法术升级额度调整，默认增加 **50** 点。
- 可选的游戏启动永久额度补丁；已安装时禁用临时加点。
- 修改前备份存档，写入前后核对数值，保留本地操作记录。
- 无终端窗口的图形启动方式。

仅适配 Windows x64、Python 3.11+ 和上述游戏版本。并非通用修改器；匹配失败时会停止写入。项目不包含游戏程序、资源、存档或 CE 源码。

## 快速开始

在 Windows 安装 64 位 Python，确保包含 Tkinter。在项目目录中运行：

```powershell
python -m ghostvalue
```

不想显示终端窗口，可双击 `GhostValue.pyw`（需要 Python 文件关联），或运行：

```powershell
pythonw GhostValue.pyw
```

也可以安装图形入口：

```powershell
python -m pip install -e .
```

安装后使用 `ghostvalue` 图形入口。仓库不包含绑定开发者机器的快捷方式；本机已有快捷方式可继续使用。

程序会查找 Steam 游戏库。如果未找到或有多个游戏副本，可在启动前明确指定：

```powershell
$env:GHOSTVALUE_GAME_DIR = "D:\Games\Kingdom Rush Genesis"
pythonw GhostValue.pyw
```

连接游戏，进入关卡，输入目标金币并点击“设置金币”。金币只修改一次，之后仍正常获得与扣费。手动筛选保留为备用功能。

## 升级点与备份

临时额度重启后会消失，而已购买升级可能保存在存档中，导致负点数。如需每次启动保留额度，参见[永久补丁说明](docs/permanent-patch.md)。

源码运行的数据保存在 `.local/`；安装为包后默认保存在 `%LOCALAPPDATA%/GhostValue`。可用 `GHOSTVALUE_DATA_DIR` 指定数据目录。该目录包含个人存档、游戏备份和日志，**不要提交或发布**。

恢复存档前正常退出游戏并另备份当前存档。仅恢复 ZIP 中的原始存档文件，不要复制 `_ghostvalue_manifest.json`；恢复后检查 Steam 云同步和实际加载的进度。

## 项目目录

```text
ghostvalue/       程序包
tests/            测试
tools/            可选本地研究工具
docs/             架构及使用文档
.github/workflows/ Windows 测试流程
.local/           本地数据（忽略、不发布）
GhostValue.pyw    图形启动入口
pyproject.toml    包配置
LICENSE          MIT 许可证
```

测试：

```powershell
python -m unittest discover -s tests -v
```

涉及真实游戏备份的集成测试在缺少本地文件时跳过。当前适配版本已人工验证金币显示/扣费，以及三类升级的购买、重置和永久补丁启动；不代表其他版本同样有效。

参见[架构说明](docs/architecture.md)和[贡献指南](CONTRIBUTING.md)。

## 许可证

本项目原创代码采用 [MIT](LICENSE)。游戏及相关资源不属于本项目，也不受该许可证授权；本项目与游戏开发商无隶属关系。
