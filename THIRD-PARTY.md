# 第三方来源

本项目自身代码及修改后的 Weasel 原生组件按 GPL-3.0 分发，完整文本见 [LICENSE](LICENSE)。第三方组件与数据保留各自许可证或权利说明。

| 组件或数据 | 来源与版本 | 许可或说明 |
| --- | --- | --- |
| Weasel | [rime/weasel](https://github.com/rime/weasel)，0.17.4 | GPL-3.0；修改后的原生源码在 `vendor/weasel`，产品扩展与探针在 `native` |
| librime | [rime/librime](https://github.com/rime/librime)，1.13.1 | BSD-3-Clause |
| Boost | [boost.org](https://www.boost.org/)，1.84.0 | Boost Software License 1.0 |
| rxi/json.lua | [rxi/json.lua](https://github.com/rxi/json.lua) | MIT，见 `vendor/rxi-json/LICENSE` |
| 历史 Rime stroke 方案 | [rime/rime-stroke](https://github.com/rime/rime-stroke) | LGPL-3.0，见 `vendor/rime-stroke/LICENSE`；不作为当前产品包默认数据 |
| 产品笔画数据 | 微信输入法 Android 4.0.0，由项目所有者提供并指定使用的静态快照 | 原始权利归各自权利人，不归入项目代码 GPL 授权；输入与生成哈希见 `packaging/provided-data.lock.json` |
| Python | [python.org](https://www.python.org/)，安装包内置 3.13.12 | PSF License |
| PyYAML | [yaml/pyyaml](https://github.com/yaml/pyyaml)，6.0.3 | MIT |
| OpenCC | [BYVoid/OpenCC](https://github.com/BYVoid/OpenCC) | Apache-2.0 |
| WinSparkle | [winsparkle.org](https://winsparkle.org/)，0.8.1 | MIT |

安装包内的 `THIRD-PARTY.txt` 和 `licenses/` 包含相应发行说明。Release 附件中的 `source.zip` 保留该安装包的确切构建源；仓库 main 包含公开目录布局与后续开发整理。
