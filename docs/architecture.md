# 代码结构

| 位置 | 职责 |
| --- | --- |
| `ghostvalue/app.py` | Tkinter 界面、后台任务和状态显示 |
| `ghostvalue/core.py` | Windows 进程与内存访问、存档备份、升级表操作 |
| `ghostvalue/lua_memory.py` | LuaJIT 对象读取、当前关卡金币定位 |
| `ghostvalue/spell_budget.py` | 当前适配版本的法术临时额度 |
| `ghostvalue/permanent_patch.py` | 原文件备份、永久额度补丁构建、安装和恢复 |
| `ghostvalue/paths.py` | 游戏路径发现与本地数据目录 |
| `ghostvalue/launcher.py` | 无终端窗口入口与错误记录 |
| `tests/` | 单元测试、可选本地集成测试 |
| `tools/inspect_game.py` | 对自己的游戏副本进行只读 Lua 字节码检查 |
| `.local/` | 本地日志、存档和游戏备份、研究记录；不发布 |

金币通过 Lua 全局环境和游戏模块找到当前关卡状态中的 `player_gold`。每次写入重新核对关卡身份；仅在写入前确认数值已变化且尚未写入时有限重试。写入后的正常扣费不会触发再次覆盖。这仍是进程外的读写，不是与游戏逻辑同步的原子事务。

英雄和塔的临时额度通过完整配置表识别。法术临时额度以源版本和函数字节码指纹为前提。永久补丁则在本地游戏包中保留原模块，通过启动包装逻辑加载固定额度；不分发修改后的游戏或原始模块。

底层 LuaJIT 2.0 布局和指令格式参考官方 [lj_obj.h](https://github.com/LuaJIT/LuaJIT/blob/v2.0/src/lj_obj.h) 与 [lj_bc.h](https://github.com/LuaJIT/LuaJIT/blob/v2.0/src/lj_bc.h)。其他版本的支持需要重新研究及测试。
