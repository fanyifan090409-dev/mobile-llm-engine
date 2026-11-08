# TestFlight 外壳 v1（模型库 + 关于与隐私）

> 日期：2026-11-03　状态：实现完成，待真机验收（18 Pro Max 跑分矩阵结束后安装）
> 前置：`首启跑分向导-v1.md`、`运行档位选择-v1.md`

## 目标

把当前演示壳补成可分发给外部 TestFlight 测试者的产品外壳：用户能自己导入 GGUF 模型、管理本机模型文件、查看版本与隐私说明。推理与数据仍全部留在本机。

## 范围（v1）

1. **模型库**（设置 → 模型库）
   - 列出 Documents/Models 与 App 内置的全部 `.gguf`（动态扫描，不再只认内置清单）
   - 排序按内置推荐顺序，用户导入的模型排最后
   - 每行显示：名称、体积、权重、按当前上下文档位估算的峰值内存、速度口径、内置/导入标签
   - 当前模型打勾；点按切换（复用 `switchModel`，保留对话历史）
   - 左滑删除：内置模型与正在使用的模型不可删
   - 从「文件」App 导入 `.gguf`（fileImporter + 安全作用域），后台拷贝，导入中显示遮罩；重名拒绝
   - 底部显示已安装数量、占用、设备可用空间
   - 「获取模型」入口跳 GitHub Release，说明浏览器官网下载→存「文件」→导入
2. **关于与隐私**（设置 → 关于与隐私）
   - 版本/构建号、系统版本、推理引擎、当前模型/上下文/速度档/设备分
   - 隐私声明：本机推理、不收集、不上传；删除 App 即清除
   - 开源致谢：llama.cpp（MIT）、Qwen3（Apache 2.0，模型基于 Qwen3 继续训练）、GitHub 项目主页
3. **设置入口**
   - 顶栏档位胶囊加齿轮图标，点按进「设置」（原「运行设置」）
   - 设置页新增「更多」：模型库、关于与隐私
4. **空态**
   - 首次进入且无对话时，聊天区显示「试试下面的示例，或直接提问 / 全部在本机推理，数据不出设备」

## 数据与存储

- 模型文件：`Documents/Models/*.gguf`（可写）与 App bundle `Models/`（只读，随包分发）
- 同名文件 Documents 优先于 bundle（用户可覆盖内置档位）
- 用户选择仍存 `UserDefaults.modelFile`（现有键，不改）
- 删除/导入后 `DemoModel.modelRevision` 自增，驱动模型库列表刷新

## 代码落点

- `apps/ios-shell/Sources/DemoChatView.swift`：DemoModel 增加动态扫描、`InstalledModel`、导入/删除/切换、`ModelLibraryError`
- `apps/ios-shell/Sources/ProductShell.swift`（新）：`ModelLibraryView`、`AboutView`
- 工程注册：project.pbxproj 四个必要条目（BuildFile/FileReference/Group/Sources）

## 回滚点

- 单文件回滚：删除 ProductShell.swift + 撤销 pbxproj 四条注册 + 设置页「更多」Section 即回到纯演示壳
- 模型扫描改动只影响档位列表来源，运行链路（load/switch）未改

## 验收

- `xcodebuild` 编译通过（2026-11-03 ✅）
- 18 Pro Max 真机：设置 → 模型库列表、切换、导入（用一个 0.6B 文件）、删除、重启后选择保持
- 关于页版本/隐私/链接显示正常

## 后续（不在 v1）

- App 图标与启动图、展示名
- 模型下载器（CDN/Release 链接）替代手动导入
- 隐私政策 URL、App Store Connect/TestFlight 配置、中国大陆上架备案
