#!/usr/bin/env node
// CAS 批量计算：给 math_eval SFT 数据生成器用。
// 输入 requests.jsonl：{id, op, expr?, variable?, lower?, upper?, stat_op?, data?, expected_expr?}
// 输出 results.jsonl：{id, status, result, latex, numeric, ms, match?}
// expected_expr 存在时用 __casCompare 按采样点数值对拍（判分口径同 score_math_eval.py）。
const fs = require('fs');
const path = require('path');

const resources = path.resolve(__dirname, '../../apps/demo-cli/Sources/demo-cli/Resources');
global.math = require(path.join(resources, 'math.js'));
eval(fs.readFileSync(path.join(resources, 'MathEvalBridge.js'), 'utf8'));

const [input, output] = process.argv.slice(2);
if (!input || !output) {
  console.error('用法: node cas_batch.js requests.jsonl results.jsonl');
  process.exit(1);
}

const lines = fs.readFileSync(input, 'utf8').split('\n').filter(l => l.trim());
const results = [];
for (const line of lines) {
  const r = JSON.parse(line);
  const data = JSON.parse(__casEval(
    r.op || 'eval', r.expr || '', r.variable || 'x',
    r.lower ?? '', r.upper ?? '', r.stat_op || '', r.data || ''));
  const row = {
    id: r.id,
    status: data.status,
    result: data.result,
    latex: data.latex || '',
    numeric: !!data.numeric,
    ms: data.ms || 0,
  };
  if (r.expected_expr) {
    const cmp = JSON.parse(__casCompare(data.result, r.expected_expr, r.variable || 'x', 1e-6));
    row.match = cmp.status === 'ok' && cmp.result === 'true';
    row.matched = cmp.matched || 0;
    row.mismatched = cmp.mismatched || 0;
  }
  results.push(JSON.stringify(row));
}
fs.writeFileSync(output, results.join('\n') + '\n');
console.log(`CAS_BATCH_DONE n=${results.length}`);
