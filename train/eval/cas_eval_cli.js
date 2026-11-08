#!/usr/bin/env node
// 单次 CAS 调用：stdin 读一个 JSON 请求，stdout 回一条 JSON 结果。
// 给端到端评测用（模型发工具调用 → 评测脚本执行真实 CAS）。
// CAS_RESOURCES 指向 math.js / MathEvalBridge.js 所在目录，默认仓库内 CLI 资源目录。
const fs = require('fs');
const path = require('path');

const dir = process.env.CAS_RESOURCES ||
  path.resolve(__dirname, '../../apps/demo-cli/Sources/demo-cli/Resources');
global.math = require(path.join(dir, 'math.js'));
eval(fs.readFileSync(path.join(dir, 'MathEvalBridge.js'), 'utf8'));

let input = '';
process.stdin.on('data', (d) => { input += d; });
process.stdin.on('end', () => {
  const r = JSON.parse(input);
  const out = JSON.parse(__casEval(
    r.op || 'eval', r.expr || '', r.variable || 'x',
    r.lower ?? '', r.upper ?? '', r.stat_op || '', r.data || ''));
  process.stdout.write(JSON.stringify(out));
});
