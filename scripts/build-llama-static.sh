#!/usr/bin/env bash
# 构建 llama.cpp 静态库（Metal 开、共享关），产物拷入 engine/Sources/CLLaMA/
# 钉版：tools/llama.cpp 为浅克隆（tag b11857），本脚本不改 tag、不动现有 build/（评测链在用）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/tools/llama.cpp"
BUILD="$SRC/build-static"
DST="$ROOT/engine/Sources/CLLaMA"

cmake -S "$SRC" -B "$BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=14.0 \
  -DGGML_METAL=ON \
  -DBUILD_SHARED_LIBS=OFF \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_EXAMPLES=OFF \
  -DLLAMA_BUILD_TOOLS=OFF \
  -DLLAMA_BUILD_SERVER=OFF

# 只构建 llama 库目标：app/ 统一 CLI 目标在浅克隆+静态配置下会因 build-info.h/arg.h 生成失败，
# 且 M1 只需要 libllama.a + libggml*.a，工具链沿用现有 build/（动态版，评测链在用）
cmake --build "$BUILD" --config Release -j "$(sysctl -n hw.ncpu)" --target llama

mkdir -p "$DST/lib" "$DST/include"
# 静态库真实落点（b11857 实测）：libllama.a 在 src/，ggml 核心在 ggml/src/，
# blas/metal 后端各在 ggml/src/ggml-{blas,metal}/ 子目录
cp "$BUILD/src/libllama.a" "$DST/lib/"
cp "$BUILD"/ggml/src/libggml*.a "$DST/lib/"
cp "$BUILD"/ggml/src/ggml-blas/libggml-blas.a "$BUILD"/ggml/src/ggml-metal/libggml-metal.a "$DST/lib/"
cp "$SRC/include/llama.h" "$SRC/include/llama-cpp.h" "$DST/include/"
cp "$SRC"/ggml/include/ggml.h "$SRC"/ggml/include/ggml-alloc.h "$SRC"/ggml/include/ggml-backend.h "$SRC"/ggml/include/ggml-cpu.h "$SRC"/ggml/include/ggml-metal.h "$SRC"/ggml/include/ggml-opt.h "$SRC"/ggml/include/gguf.h "$DST/include/"
echo "静态库构建完成："
ls -la "$DST/lib/" "$DST/include/"
