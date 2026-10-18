# 小狼毫原生设置入口

当前鼠标模式由后台唯一拥有 `BihuaMousePanel`，开关是编译 weasel 配置中的 `bihua_mouse/enabled`。第一行输入、翻页、回退，右侧圆角框显示非空笔画，候选和联想默认一行，右侧可展开成五行，只有第一行编号及数字选字，其余行用鼠标点选。退格点击宽度为普通按钮两倍；问号同笔画缩至84%，线宽保持一致。0.6.17 的前端 0.5.9 通过已认证的 IPC 报告 profile 激活/停用，后台按前台 PID、输入线程及会话匹配控制显隐，切换其他输入法隐藏、切回恢复；仅在后台查询活动 profile 无法可靠覆盖真实 32 位切换。无可写焦点、只读、ASCII或其他输入法时隐藏，恢复可写焦点时显示；短暂待执行只禁用交互。前端在所属UI线程每150ms检查动态只读/焦点，仅在上下文改变时发送显隐IPC，不在轮询中刷新候选。隐藏不替代写入校验。字号、候选间距和 DPI 共同决定绘制与命中几何，窗口 region 具有实际圆角，GDI+ 对边框进行抗锯齿，按钮边框及交互使用背景色上黑/白的透明度混色。笔画组仅横键左侧、问号键右侧各扩展8 DIP留白和点击/hover区域，内部核心键宽及图标中心间距不变。退格是动作 17，只处理 Rime 未提交的组字，不向应用模拟 Backspace。`BihuaMouseState` 将点击绑定到焦点代次及候选投影版本，输入/翻页在修改Rime前使旧点击失效。后几行按过滤后真实绝对索引选择，经显式选择协议保留词库学习。后台最多预取5N项；只有面板真实绘制并确认的范围，才在下次Rime动作前合并到现有曝光回合，重复绘制不会重复扣分。新版 TSF 在取得当前 context 的读写 edit cookie 后执行已认证的 IPC 动作并直接上屏，新模式不模拟操作系统按键。详见 `docs/feature-architecture/2026-10-17-2109-鼠标常驻两行笔画面板架构.md`。

以官方 [Weasel 0.17.4](https://github.com/rime/weasel/tree/0.17.4) 为基础，Boost严格使用1.84.0，Rime导入库及运行库使用1.13.1。来源与校验信息见UPSTREAM.json。原源码GPL-3.0，保留许可证；补丁在weasel-0.17.4-bihua.patch，固定启动器和失焦适配源码在本目录。

0.5.1 的托盘和语言栏菜单只保留40018「笔画输入法」与40017「笔画设置」。前者明确激活 bihua_mvp 并开启简体中文模式，后者启动本地设置页。语言栏沿用通用TrayCommand转发，不改IPC结构和数据序列化版本。TSF使用原安装DLL的副本，仅改MENU资源；Verify-Native-Settings.py检查两种位数COM真实加载、九个菜单资源恰好两项及可执行段逐字节一致。

本机VS2022包含ATL、不包含MFC；资源头改为Windows SDK winres.h即可编译。构建目录位于项目忽略的.verification/weasel-native，无新worktree。中文路径曾影响Boost b2，因此构建时使用经核对的短SUBST路径。Patch-Native-Source.py对解包的固定源码应用补丁；Boost构建七类静态依赖后，MSBuild编译Release/x64的WeaselServer。BihuaSettingsLauncher.cpp使用同一工具链、/MT、/SUBSYSTEM:WINDOWS独立编译。FocusBoundaryProbe.cpp与生产Server共用BihuaFocusBoundary.h。

在原补丁后执行 `python scripts/Patch-Single-Menu.py`，重新构建 Server，并用 Patch-Native-Menus.py 把两个原版 TSF DLL 的菜单写入 package-0.5.1。升级已有0.5.0：`python scripts/Upgrade-Native-Menu.py --apply`；新装：`python scripts/Install-Native-Settings.py --apply`。当前用户包位于%LOCALAPPDATA%/BihuaWeasel/0.5.1；原Program Files安装不覆盖。专属共享数据目录仅保留 bihua_mvp.schema.yaml，保留所需词典及转换数据。HKCU两种注册表视图分别覆盖原CLSID的InprocServer32；原值及文件哈希保存在installation.json。设置页面由项目scripts/Open-Settings.ps1启动，固定本地脚本路径保存在同目录settings-script.txt。

恢复命令：`python scripts/Install-Native-Settings.py --restore`。先完整核对注册值，外部冲突不做部分恢复。只删除自己创建且仍为空的子键；恢复旧服务并保留包和历史收据。普通设置部署及个人词库备份另有独立恢复机制。

原生设置命令验证：`WeaselServer.exe /bihua-settings`，走与菜单点击相同的IPC/handler；settings-last-launch.json记录启动器结果。`/bihua-enable`激活方案；`/bihua-reload`为开发维护入口。`/bihua-engine-probe`仅创建和关闭空会话，不发送按键、不提交文字，要求真实响应含status.schema_id=bihua_mvp，并记录bihua-engine-session.txt。设置保存使用本用户包的WeaselDeployer，避免使用其他共享方案目录。

FocusOut设置中性边界；仅当Lua明确标记当前菜单为本方案联想，且输入长度为0、有候选时才清菜单。普通未完成笔画不提交也不清除。已用真实1.13.1会话和同一C++helper验证；没有代替用户操作桌面做跨应用键盘测试。

已加载旧DLL的应用需要重新打开才能看到新语言栏菜单；托盘由当前新Server提供。HKCU自启动直接启动本包。后台从操作系统管道句柄取得来客PID及可执行路径，拒绝其他目录WeaselServer.exe发出的关闭请求，阻止原版启动或缓存旧菜单重启夺回服务。当前包/q正常退出，升级必须先用当前版本/q再启新包。真实原版晚启动竞争、当前包退出重启、维护重载及设置保存均通过；实际注销登录未测试。这个后台进程是小狼毫的架构组件，并非Windows系统服务。

2026-10-14 用户再次反馈复杂菜单：实际 explorer.exe 仍载入 C:/Windows/System32/weasel.dll，说明新进程COM探针不能替代任务栏宿主验收。核对当前用户及会话后重新加载任务栏，explorer.exe 已载入用户0.5.1/weaselx64.dll，后台真实会话仍通过。Verify-Native-Settings.py现要求检查实际任务栏模块，旧DLL或尚未加载不再记为完整通过。


## 2026-10-15 独立安装修复

独立 Windows 前端 0.5.3 使用自己的 TSF 身份，后台 0.5.2 从 Windows 登录任务启动。真实用户目录和当前进程加载已通过外部验收。回车确认后收起候选，空格继续联想。此前 0.5.1 开发视图报告不等同实际 Windows 安装。详细证据和发行限制见 docs/安装与发行.md。


按键风格的物理键归一化由 bihua_query_keys 完成，递归注入标准键后沿用原学习与选择处理。原生 FocusOut 无条件设置 bihua_keymap_reset，以保证关闭联想时点选字状态也不残留。设置入口默认内置 Python Native-Settings.py Win32 窗口，保留 Open-Settings.ps1 -Web 兼容路径。

笔画工具按钮使用独立的紧凑间距，不继承候选字间距；预编辑框占满右侧剩余宽度，按实际字体宽度保留可显示的最新笔画，省略时仅在左侧提示，UTF-16代理对不可拆分。九个工具图标全部采用同一矢量画布和线宽，等宽等高；笔画与通配共用圆角框，翻页共用胶囊框，退格独立成键，悬停时显示单键范围。

五种笔画图标的视觉比例为原画布的 84%，保持线宽、居中和按键点击范围；问号、翻页与退格图标不随之缩小。

鼠标模式的 Return 在四个 TSF KeyEventSink 入口直接放行，包含主键盘、小键盘及按下／释放；不调用 Rime、不执行更新编辑会话，不改变组字、候选或联想。键盘模式保留原确认语义。受控真实编辑器见 MouseEditorProbe.cpp。

鼠标模式的键盘路由由 `BihuaKeyboardRoute` 独立控制，不翻转 Rime ASCII。Shift 单击释放或无修饰 Tab 切换；组合键透传，英文按键绕过 Rime 与组字更新。`BihuaMouseView` 在后台统一维护展开和绝对导航索引，UI仅镜像；箭头先同步更新后台，再由 Space/KP0 经过原 TSF 安全管线确认，Enter 透传、数字只第一行。设置键 `bihua_mouse/stroke_info` / `arrow_navigation` 默认开启。长按500ms只读安装目录校验后的当前canonical默认表，浮层无激活、短按/长按分离，输入/导航/失焦取消旧手势。绝对选字期间禁止Lua按目标页臆造曝光，仅合并真实UI确认。
