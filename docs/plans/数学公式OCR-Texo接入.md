# Texo 公式 OCR 接入（iOS，2026-11-09）

> 目标：拍照识别数学公式，替代纯 Vision 文本路径的上下标丢失问题。
> 状态：代码完成，Mac 18 图对拍全过、真机目标构建通过；真机相册联调待手机接入。

## 决策与选型

- 模型：**Texo-distill**（20M 参数，ONNX：encoder 52MB + decoder 25MB，tokenizer 17KB）；
  UniMERNet BLEU SPE 0.9014 / CPE 0.8909；本机 18 张渲染图实测 14/18 完全正确、sim 0.961、51ms（M5 CPU）。
- 运行时：**ONNX Runtime 1.28.2**——直接用 sherpa-onnx 已依赖的 `onnxruntime-libs` SPM 产品
  `onnxruntime-ios`（静态 xcframework，MIT）。曾尝试另链 1.30.0，会与 sherpa 的 1.28.2
  重复定义 ORT 符号且 API 版本错配，已放弃。
- C 头文件 vendored 在 `apps/ios-shell/Frameworks/onnxruntime-headers/`（1MB，随 git 入库），
  只链 CPU EP，不启用 Core ML EP。
- 许可证：Texo 权重 AGPL-3.0，项目整体按 AGPL-3.0 发布（用户已确认开源）。
- 中文题干仍走 Apple Vision（Texo 只认公式，不认中文）。

## 资产与目录

- `apps/ios-shell/FormulaOCR/encoder_model.onnx`（52MB）、`decoder_model.onnx`（25MB）、`tokenizer.json`
- `scripts/fetch_texo_assets.sh`：从 hf-mirror.com / huggingface.co 的 `alephpi/FormulaNet` 拉取并 SHA-256 校验；
  `.gitignore` 排除 `apps/ios-shell/FormulaOCR/`，新机器先跑脚本。
- ORT 不占仓库体积：由 `onnxruntime-libs` SPM 包在构建时下载。

## 代码落点与契约

- `Sources/TexoRunner.h/.mm`（ObjC++）：封装 ORT C API，暴露
  `-initWithEncoderPath:decoderPath:error:` 与 `-generateTokensWithPixels:maxLength:error:`
  （入参 float32 NCHW 3×384×384，返回 token id 数组，不含起始/eos；encoder hidden 跨解码步复用）。
- `Sources/TexoOCR.swift`：UIImage 预处理（修 EXIF 方向 → 长边 ≤1600 → 去白边 →
  长边缩到 384 → 居中黑边 pad → PIL 同款 ITU-R 601-2 灰度 → mean 0.7931/std 0.1738 → 复制 3 通道）
  + WordLevel 解码（vocab 687，token 直接拼接）+ 资源懒加载（77MB 模型首次加载约 1–3s，后台队列）。
- `Sources/FormulaText.swift`：LaTeX→题意（纯 Foundation，29 例单测全过）：
  - 方程 `x^{2}-5x+6=0` → `解方程 x^(2)-5*x+6=0。`
  - 定积分 `\int_{0}^{1}x^2\,dx` → `求 x^(2) 从 0 到 1 的定积分。`
  - 导数 `\frac{d}{dx}(x^3+2x)` → `求 (x^(3)+2*x) 关于 x 的导数。`
  - 极限 `\lim_{x\to0}\frac{\sin x}{x}` → `求 ((sin(x))/(x)) 在 x→0 时的极限。`
  - 组合数 / 求和 / 其他表达式 → `计算 …。`
  - 已处理 Texo 的典型坏格式：`\mathsf{s i n}`、`c o s`、`\sinx`、`{\int}`、`^{\prime}`、`109_{2}`（log 误读）。
- `Sources/DemoChatView.swift`：照片导入并行跑 Vision + Texo；两路都有结果时把公式题意接在
  中文题干后（`looksMathematical` 过滤纯文字照片的噪声），输入框始终可编辑，保留人工改错。
- `EngineShell-Bridging-Header.h` + `SWIFT_OBJC_BRIDGING_HEADER` 暴露 ObjC++ 类；
  `HEADER_SEARCH_PATHS` 指向 vendored ORT 头文件；`OTHER_LDFLAGS` 补 `-lc++` 与 CoreML 等系统框架。

## 回滚点

- 移除 `DemoChatView.importPhoto` 里的 Texo 分支 + 删 `TexoOCR/TexoRunner/FormulaText` 三个源文件、
  `FormulaOCR` 资源与 `onnxruntime-ios` 产品依赖，即回到纯 Vision 路径。
- 不改 EngineKit 与 sherpa-onnx 的任何代码。

## 验收

1. ✅ `xcodebuild -destination 'generic/platform=iOS'` 编译通过（模拟器因 llama 静态库只有 device slice，历史不支持）。
2. ✅ Mac 侧同源 Swift/ObjC++ 跑 18 图：输出与 Python ONNX 推理逐字一致（空白归一后），
   单张 33–63ms（含预处理与贪心解码）。
3. ⏳ 真机：相册选公式照片 → 输入框出现可编辑题意 → SFT27e 调 math_eval 出答案；飞行模式可用。
4. ⏳ 真机延迟/内存：目标单张 < 1.5s、内存峰值增量 < 150MB（当前手边无已连接设备）。
5. ⏳ 回归：13/13 工具场景不受影响（math 工具仅 sft27 模型白名单启用）。

## 风险

- App 体积 +77MB（ONNX 权重），首启加载 ORT session 占内存；只在 App target 链接。
- Texo 对手写/复杂多栏排版有限；演示选打印体、单行公式。
- `\log_2` 类下标函数会读成 109_2；已加 `^109_{` → `\log_{` 的窄修正，其他误读需人工改。
- AGPL：分发 App 需提供完整对应源码（本仓库即源码）；上架 App Store 与 AGPL 条款存在冲突，
  仅作 GitHub/TestFlight 分发。
