#!/usr/bin/env bash
# 拉取公式 OCR 的 Texo ONNX 权重（AGPL-3.0，约 76MB）。
# ORT 静态库由 sherpa-onnx 的 SPM 依赖（onnxruntime-libs 1.28.2）提供；
# 对应 C 头文件已 vendored 在 apps/ios-shell/Frameworks/onnxruntime-headers。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/apps/ios-shell"

HF_REPOS=("https://hf-mirror.com/alephpi/FormulaNet/resolve/main"
          "https://huggingface.co/alephpi/FormulaNet/resolve/main")
# 与 alephpi/FormulaNet 的 ONNX 导出（2026-11-09 实测）
FILES=("encoder_model.onnx:fbd69cf63cf833db1e2ef40013d859b560671c1253278441a01bde4516b624ae"
       "decoder_model.onnx:00f07add62d74c78750cfda60ce8f1cff3d1774f913ca3f412e2e72f4189d7d4"
       "tokenizer.json:1240f9d178e1ad2a0076fe95ba62e332871c702accdd5ce3ae3ef33ffd6c3a1e")

FORCE=false
[[ "${1:-}" == "--force" ]] && FORCE=true

mkdir -p "$APP/FormulaOCR"

check_sha() {
    local file="$1" expected="$2" actual
    actual="$(shasum -a 256 "$file" | awk '{print $1}')"
    [[ "$actual" == "$expected" ]] || { echo "校验失败：$file（got $actual）" >&2; return 1; }
}

for entry in "${FILES[@]}"; do
    name="${entry%%:*}"
    sha="${entry##*:}"
    target="$APP/FormulaOCR/$name"
    if [[ "$FORCE" == false && -f "$target" ]] && check_sha "$target" "$sha" 2>/dev/null; then
        echo "$name 已存在，跳过"
        continue
    fi
    ok=false
    for base in "${HF_REPOS[@]}"; do
        echo "下载 $name ← $base"
        if curl -L --fail --retry 2 -o "$target.tmp" "$base/$name"; then
            mv "$target.tmp" "$target"
            ok=true
            break
        fi
    done
    [[ "$ok" == true ]] || { echo "下载失败：$name" >&2; exit 1; }
    check_sha "$target" "$sha"
    echo "$name 就绪"
done

echo "Texo 资产就绪。打开 Xcode 构建即可。"
