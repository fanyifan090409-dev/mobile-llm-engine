# iOS 测试壳计划（apps/ios-shell）

> 目的：真机验证链——EngineKit 在 iPhone 上真正跑起来（加载 GGUF → 推理 → 出字），为 #31 真机跑分铺路。
> 用户已批准 iOS 测试线（「开吧」）；本计划为落笔版。

## 范围与非目标

- 范围：最小 SwiftUI 壳——输入框 + 运行按钮 + 输出区 + 文件日志落盘。
- 非目标：模拟器（官方脚本只产了 device 切片，模拟器需另编 sim 库且 SwiftPM 无法按 device/sim 条件选库——真机是目标，模拟器跳过）；UI 美化；多模型切换。

## 接口契约（壳只依赖 EngineKit 公开 API）

- 推理入口：EngineKit 公开 API（与 apps/demo-cli 同款用法，写码前先读 demo-cli 源码对齐）。
- 日志落盘：`Documents/engine-shell.log`，每行带时间戳；UI 同时滚动显示。真机无控制台，文件是唯一证据链。
- 模型装载：优先 `Documents/` 下的 .gguf，找不到则用 App bundle 内嵌模型（Q5_K_M 551MB 打进 bundle，测试期最省事）。
- 速度档：默认 balanced（后续真机矩阵再扫四档）。

## 目录结构（纯新增，不动 engine/）

```
apps/ios-shell/
  EngineShell.xcodeproj/project.pbxproj   # 手写最小 pbxproj（objectVersion 56，无 xcodegen 依赖）
  Sources/
    EngineShellApp.swift                  # @main SwiftUI App
    ContentView.swift                     # 输入框/按钮/输出区
    AppLog.swift                          # 文件日志（时间戳 append）
  Models/                                 # 文件夹引用（蓝目录）打进 bundle；.gguf 不入 git
```

## 工程配置

- 本地包引用：XCLocalSwiftPackageReference → `../engine`，产品 EngineKit。
- GENERATE_INFOPLIST_FILE=YES + UILaunchScreen 生成；iOS 下限 17.0（库按 16.4 编译，对齐 engine/Package.swift）。
- 签名：CODE_SIGN_STYLE=Automatic；无账号环境下用 CODE_SIGNING_ALLOWED=NO 做编译门禁，真机安装时用户在 Xcode 里用个人 Apple ID 免费签名（7 天）。

## 验证

1. `xcodebuild -sdk iphoneos CODE_SIGNING_ALLOWED=NO build` 全绿（编译 + 链接 = iOS 库真链接验证）。
2. 用户插 iPhone → Xcode 装壳 → 输入一句话 → 出字 + Documents/engine-shell.log 有记录。
3. 通过后升级为跑分壳（四档扫描 + 工具调用题），即 #31。

## 回滚点

- 纯新增目录 apps/ios-shell/ + .gitignore 一行；失败直接删目录，engine/ 与 Mac 链路零影响。
- 每个可验证增量一个 commit（先工程+代码编译过，再装模型实测）。
