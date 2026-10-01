# 参与开发

使用 Windows 和 64 位 Python 3.11 或更新版本。项目运行时仅依赖 Python 标准库及 Tkinter。

```powershell
python -m unittest discover -s tests -v
python -m ghostvalue
```

`tests/test_patch_wrappers.py` 是本地集成测试，需要自己的游戏副本及已生成的补丁备份；缺少这些条件时自动跳过，普通测试不需要游戏。

提交改动时说明触发场景、最终行为、测试结果和仍未验证的游戏版本。内存写入必须保留对象身份核对、原值检查和读回，不应在匹配不唯一时猜测地址。永久补丁必须保留原文件、验证游戏版本并可恢复。

请勿提交游戏 EXE、DLL、提取出来的游戏脚本、资源、存档、截图中的私人信息或本机日志。运行数据位于 `.local/`，已忽略；发布源代码包时也会排除。MIT 仅适用于本项目作者贡献的代码，不涵盖游戏及其资源。

当前没有设定公开仓库地址；项目发布后再通过对应仓库的 issue 和 pull request 协作。
