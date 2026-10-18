# 0.6.28 测试版构建

源代码包的 `weasel-0.17.4` 是实际修改后的前端和后台源码；`project` 是笔画算法、设置、安装与补丁工具，`data/provided-wetype` 是用户指定的微信数据快照，`dependencies/boost_1_84_0.7z` 是所用 Boost 完整上游源码归档。前端按 Weasel 的 GPL v3 分发，第三方数据的权利说明见 THIRD-PARTY.txt。Microsoft Windows SDK、ATL 和编译器须自行安装。

1. 使用 VS 2022 v143、Windows SDK、ATL，依据 Weasel 的 INSTALL.md 配置 WTL、Boost 1.84、Rime 1.13.1 库。Release x64 构建 WeaselServer、WeaselDeployer；Release x64 与 Win32 分别构建 WeaselTSF。补丁中的身份须与 native/bihua-profile-identity.json 相同。编译器使用 /MT。项目没有依赖 Codex 的运行接口。
2. 当前仓库直接从 `data/provided-wetype` 读取固定快照，可运行 `python scripts/Build-Provided-Profile.py` 生成隔离的 profile。Build-Release.py 调用 release_profile.py 校验 `packaging/provided-data.lock.json` 并生成字码、前缀排序、词组和逐字联想；四张核心表须与已验证参考表逐字节相同。缺失或不一致即停止，不回退 Conway 或读取真实用户资料。Build-Release.py 列出本机构建目录布局及白名单；其他机器需准备对应依赖产物。Python 嵌入包为官方 3.13.12 x64，另放置 PyYAML 6.0.3 纯 Python 模块。若重建 Release 附件内的原始 0.6.28 快照，其旧脚本仍要求将数据放到 `.verification/wetype-mobile/reproducible-export`；该路径差异不改变输入与生成结果。
3. 将 SetupBootstrap.cpp、build-bootstrap.cmd、setup.rc 放到一个 ASCII 构建目录。先运行 `build-bootstrap.cmd uninstall`，将 Uninstall.exe 放入 release/0.6.28。运行 Build-Release.py 生成 payload.zip 和源码包；复制 payload.zip 到同一个构建目录，运行 `build-bootstrap.cmd` 生成 setup.exe。该 exe 将 ZIP 作为资源嵌入，自行解包到当前用户目录。
4. `setup.exe /validate <全新的测试目录>` 会解包并运行真正的 Rime 与原生设置测试，不写 TSF、启动任务或真实用户资料。实际安装需要 Windows TSF 机器注册，可能出现 UAC；不能用验证模式替代干净系统安装与重启测试。

Install-Release.py 负责用户级安装事务，BihuaProfileSetup.cpp 负责需要管理员权限的机器级 TSF 注册。二者权限分开，用户词库始终放在 Rime 用户目录中。Test-Release-Transactions.py 用模拟的 Windows 接口验证回滚和数据保留。

升级统一替换产品基础表，保留独立的个人词库、个人笔顺、学习记录及 custom 设置。Test-Provided-Data.py 验证数据身份和损坏拒绝；Test-Provided-Rime.py 在全新用户目录验证真实 Rime 的默认候选，含 `12125` 首屏及前45项排序。
