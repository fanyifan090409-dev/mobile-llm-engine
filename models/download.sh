#!/usr/bin/env bash
# GGUF 下载脚本：从 models/models.json 清单拉取，断点续传 + 可选 sha256 校验
# 用法：download.sh [tag...]（不带参数 = 全部；tag 见 models.json）
# 依赖：curl、jq（无 jq 时用 python3 兜底解析）
# HF 直连被墙（训练侧惯例）：默认走 hf-mirror.com，可用 HF_ENDPOINT 环境变量覆盖
set -u
cd "$(dirname "$0")"

MANIFEST=models.json
[ -f "$MANIFEST" ] || { echo "缺少 $MANIFEST"; exit 1; }

tags=("$@")
if [ ${#tags[@]} -eq 0 ]; then
  # macOS 自带 bash 3.2 无 mapfile，用 while-read 逐行收集
  while IFS= read -r t; do tags+=("$t"); done < <(jq -r '.models[].tag' "$MANIFEST" 2>/dev/null || \
    python3 -c "import json,sys; print('\n'.join(m['tag'] for m in json.load(open('$MANIFEST'))['models']))")
fi

for tag in "${tags[@]}"; do
  if command -v jq >/dev/null 2>&1; then
    row=$(jq -c ".models[] | select(.tag==\"$tag\")" "$MANIFEST")
  else
    row=$(python3 -c "import json,sys; print(json.dumps(next(m for m in json.load(open('$MANIFEST'))['models'] if m['tag']=='$tag')))")
  fi
  [ -n "$row" ] || { echo "清单里没有 tag=$tag"; exit 1; }
  url=$(echo "$row" | jq -r .url 2>/dev/null || python3 -c "import json,sys; print(json.loads(sys.argv[1])['url'])" "$row")
  file=$(echo "$row" | jq -r .file 2>/dev/null || python3 -c "import json,sys; print(json.loads(sys.argv[1])['file'])" "$row")
  sha=$(echo "$row" | jq -r .sha256 2>/dev/null || python3 -c "import json,sys; print(json.loads(sys.argv[1])['sha256'])" "$row")
  # 清单存官方 URL，下载时替换为镜像端点
  url=$(printf '%s' "$url" | sed "s#^https://huggingface.co/#${HF_ENDPOINT:-https://hf-mirror.com}/#")

  echo "==> $tag → $file"
  if [ -f "$file" ] && [ -n "$sha" ] && [ "$(shasum -a 256 "$file" | awk '{print $1}')" = "$sha" ]; then
    echo "    已存在且校验通过，跳过"
    continue
  fi
  # -C -：断点续传；-f：HTTP 错误码也退出
  # --retry-all-errors：hf-mirror 偶发 429 限流（HF 侧 5 分钟窗口）也要重试；--retry-delay 10 指数退避
  curl -L -C - -f --retry 5 --retry-all-errors --retry-delay 10 --connect-timeout 20 -o "$file" "$url" || { echo "    下载失败：$url"; exit 1; }

  actual_sha=$(shasum -a 256 "$file" | awk '{print $1}')
  if [ -n "$sha" ]; then
    [ "$actual_sha" = "$sha" ] || { echo "    sha256 不匹配！期望 $sha 实际 $actual_sha"; exit 1; }
    echo "    sha256 校验通过"
  else
    echo "    下载完成，sha256=$actual_sha（清单未钉校验值，首次下载后请回填 models.json）"
  fi
done
echo "ALL_DONE"
