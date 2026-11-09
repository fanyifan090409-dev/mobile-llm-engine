#!/usr/bin/env bash
# FormulaText 回归：Texo 18 图实际输出 + 11 个手写边界用例。
# 纯 Foundation，不依赖 Xcode/iOS，直接 swift 跑。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat "$ROOT/apps/ios-shell/Sources/FormulaText.swift" > "$TMP/test.swift"
cat >> "$TMP/test.swift" <<'SWIFT'

let cases: [(id: String, latex: String, expected: String)] = [
    // Texo 18 图实际输出
    ("f01", "x ^ { 2 } - 5 x + 6 = 0", "解方程 x^(2)-5*x+6=0。"),
    ("f02", "3 x + 7 = 1 2", "解方程 3*x+7=12。"),
    ("f03", "{ \\frac { 1 } { 2 } } + { \\frac { 1 } { 3 } }", "计算 ((1)/(2))+((1)/(3))。"),
    ("f04", "{ \\frac { x + 1 } { x - 1 } }", "计算 ((x+1)/(x-1))。"),
    ("f05", "\\sqrt { x ^ { 2 } + 1 }", "计算 sqrt(x^(2)+1)。"),
    ("f06", "{ \\int } _ { 0 } ^ { 1 } x ^ { 2 } ~ d x", "求 x^(2) 从 0 到 1 的定积分。"),
    ("f07", "\\int \\sin x d x", "求 sin(x) 的不定积分。"),
    ("f08", "\\lim _ { x \\rarr 0 } { \\frac { \\sin x } { x } }", "求 ((sin(x))/(x)) 在 x→0 时的极限。"),
    ("f09", "\\sum _ { k = 1 } ^ { n } k", "求 k 从 k=1 到 n 的和。"),
    ("f10", "{ \\mathsf { s i n } } ^ { 2 } x + { \\mathsf { c o s } } ^ { 2 } x = 1", "解方程 sin(x)^(2)+cos(x)^(2)=1。"),
    ("f11", "f ( x ) = x ^ { 3 } - 2 x", "解方程 f(x)=x^(3)-2*x。"),
    ("f12", "f ^ { \\prime } ( x ) = 3 x ^ { 2 } - 2", "解方程 f'(x)=3*x^(2)-2。"),
    ("f13", "a _ { n } = 2 n + 1", "解方程 a_n=2*n+1。"),
    ("f14", "1 0 9 _ { 2 } ~ 3 2 = 5", "解方程 log(32,2)=5。"),
    ("f15", "e ^ { i \\pi } + 1 = 0", "解方程 e^(i*pi)+1=0。"),
    ("f16", "{ \\binom { n } { k } } = { \\frac { n ! } { k ! ~ ( n - k ) ! } }", "计算组合数 C(n,k)。"),
    ("f17", "{ \\frac { d } { d x } } ( x ^ { 3 } + 2 x )", "求 (x^(3)+2*x) 关于 x 的导数。"),
    ("f18", "\\int _ { 0 } ^ { \\pi } c o s x d x", "求 cos(x) 从 0 到 pi 的定积分。"),
    // 手写边界用例
    ("e01", "\\int x d x", "求 x 的不定积分。"),
    ("e02", "\\int_0^1 x d x", "求 x 从 0 到 1 的定积分。"),
    ("e03", "\\sqrt { x }", "计算 sqrt(x)。"),
    ("e04", "\\log_{2}32=5", "解方程 log(32,2)=5。"),
    ("e05", "\\operatorname{lim}_{x\\to0}\\frac{\\sin x}{x}", "求 ((sin(x))/(x)) 在 x→0 时的极限。"),
    ("e06", "\\left(\\frac{1}{2}\\right)", "计算 (((1)/(2)))。"),
    ("e07", "\\sum_{k=1}^{n}k^2", "求 k^2 从 k=1 到 n 的和。"),
    ("e08", "2\\pi x+1", "计算 2*pi*x+1。"),
    ("e09", "\\int_{0}^{2}(3x^2+1)dx", "求 (3*x^2+1) 从 0 到 2 的定积分。"),
    ("e10", "\\frac{d}{dx}\\sin x", "求 sin(x) 关于 x 的导数。"),
]

var failed = 0
for item in cases {
    let actual = FormulaText.problem(from: item.latex)
    if actual != item.expected {
        failed += 1
        print("FAIL \(item.id)\n  输入：\(item.latex)\n  期望：\(item.expected)\n  实际：\(actual)")
    }
}
if failed == 0 {
    print("FormulaText PASS \(cases.count)/\(cases.count)")
} else {
    print("FormulaText FAIL \(failed)/\(cases.count)")
    exit(1)
}
SWIFT

swift "$TMP/test.swift"
