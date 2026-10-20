# 笔画输入法 · BihuaInput

面向 Windows 的纯笔画输入法，基于 Rime 和 Weasel，支持键盘输入与常驻鼠标面板。

[下载 0.6.30 测试版](https://github.com/chanyuenpang/bihua-input/releases/tag/v0.6.30) · [使用说明](使用说明.md) · [构建说明](packaging/BUILD.md) · [第三方来源](THIRD-PARTY.md)

## 安装

在 Releases 下载 `BihuaInput-0.6.30-setup.exe` 并安装，按 Win＋空格切换到「笔画输入法」。安装包内置运行库和设置面板，无需安装 Codex、小狼毫或 Python。

当前为 Windows x64 测试包，包含供 32/64 位应用使用的输入法前端。已有版本可直接升级，个人词库、个人笔顺、学习记录和设置独立保留。

右键输入法图标 →「笔画设置」，可以调整键位、鼠标面板、候选翻页、本地联想、个人词库、个人笔顺及外观。外观字号会带动鼠标面板与按钮缩小，仍保留最小点击尺寸。

## 功能

- 五种笔画输入，默认简体；不必输入完整笔顺就可找字。
- 字母和小键盘分别提供两种预设，并支持按键录入自定义绑定。
- 通配符、分词及不完整多字查询；例如 `sz F sz` 或小键盘 `25 7 25` 查「中国」。
- 鼠标面板可拖动、展开五行候选、继续翻页，支持方向键导航和长按查看笔顺。
- 本地逐字联想、个人词库，以及按实际选择调整的个人反馈。
- 普通单字按实际选字学习排序：每次选中约前移 3 个基础位置，累计最多前移 60 位；跨笔画前缀、通配和个人笔顺共享同一个字的学习记录，重启后保留。
- 自定义笔顺与系统笔顺并存，沿用原字权重；保存后立即生效。
- 编辑个人笔顺时保留系统笔顺参照，输入逐笔覆盖，差异高亮，退格恢复参照。未输入的灰色笔画不自动加入保存。

![个人笔顺参照与差异高亮](assets/screenshots/personal-strokes-light.png)

## 默认按键

| 输入 | 横 | 竖 | 撇 | 点／捺 | 折 | 通配 | 分词 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 字母 | H | S | P | D，兼容 N | Z | T | F |
| 小键盘 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |

空格／小键盘 0 选字并继续联想。主键盘 1–9 选择当前页候选；小键盘按住 `.` 后再按 1–9 选字。小键盘 −／+ 翻页，Esc 取消。

没有绑定笔画、通配或分词的数字键，按从小到大依次选择当前页的前几个候选：789456 风格用 1／2／3 选第 1／2／3 项；默认风格用 8／9 选第 1／2 项。自定义绑定也自动计算空闲键。超出本页数量时不作操作。

在普通权限、可输入的前台应用中启用本输入法时，后台保持 Num Lock 数字状态并拦截误触，离开有效输入焦点或切换其他输入法时恢复原状态。该保护独立于鼠标面板开关，不写注册表或改变其他输入法的按键绑定。

键盘模式下 Enter 选字并收起候选；鼠标模式下 Enter 保留应用原有操作，不确认或清空候选。Shift 切换键盘中英文输入；Caps Lock 对应 A 状态，英文状态仍可用鼠标输入笔画。

## 产品数据

产品使用项目所有者提供并指定的微信输入法 Android 4.0.0 静态快照，统一笔顺、前缀候选排序、词组与逐字联想。输入文件在 [`data/provided-wetype`](data/provided-wetype)，固定输入和生成哈希见 [`provided-data.lock.json`](packaging/provided-data.lock.json)。缺少数据或校验不符会停止构建，不回退其他码表。

无个人历史和联想上下文时，`12125` 默认首屏为「提、喜、担、吉、博、损、扣、抽、操」，“吉”为第 4 项。这也是发布校验的一部分。

这些是产品基础数据；用户个人词库、个人笔顺与输入历史不在仓库中。第三方数据保留原始权利说明，不归入项目代码的 GPL 授权；静态查询基线不代表完整复现微信输入法的运行时算法。

## 开发与检查

使用 Python 3.13，在 Windows PowerShell 中运行：

```powershell
python -m pip install -r requirements-dev.txt
New-Item -ItemType Directory -Force .verification | Out-Null
python -B scripts/Build-Provided-Profile.py
python -B scripts/Test-Provided-Data.py
python -B scripts/Test-Personal-Stroke-Save.py
python -B scripts/Test-Release-Transactions.py
```

这些检查使用隔离目录，不需要安装输入法。GitHub Actions 执行固定数据、个人笔顺保存以及安装迁移／回滚检查。`Test-Keypad-Learning.py --runtime <解包目录>` 使用真实 Rime 验证空闲键；加 `--mode learning` 验证单字学习，`--reuse --user <先前测试目录>` 验证独立进程重启后的记录。

原生扩展和测试探针在 `native/`，修改后的 Weasel 0.17.4 源码在 `vendor/weasel/`。完整 Windows 构建还需要 VS 2022 v143、Windows SDK、ATL、WTL、Boost 1.84.0、Rime 1.13.1 及 Python 嵌入运行库；见[构建说明](packaging/BUILD.md)。现有打包工具保留开发机依赖路径，换机器构建需准备依赖并调整路径，不是一键构建流程。

Release 中的 `source.zip` 保存对应安装包的确切构建源，main 分支包含后续开发及公开目录布局整理。安装包和生成文件通过 Releases 提供，Git 保存代码、来源锁与固定数据快照。

## 验证范围

0.6.30 已验证固定数据一致性、空白用户目录中的真实 Rime 查询、`12125` 前 45 个候选、分词、通配、本地联想、原生界面和当前电脑升级。干净 Windows 首装、系统重启和跨应用物理键盘完整验收仍待补齐。GitHub CI 的源码检查不替代 Windows 桌面端验收。

## 许可

项目代码与修改后的 Weasel 按 [GPL-3.0](LICENSE) 分发。第三方组件及数据分别保留各自许可证或权利说明，见 [THIRD-PARTY.md](THIRD-PARTY.md)。
