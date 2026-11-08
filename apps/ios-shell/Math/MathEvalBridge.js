// CAS 桥接层：在 JavaScriptCore 里调用全局 math（math.js 浏览器构建已加载）。
// 只暴露 __casEval 一个函数；输入输出都是字符串/JSON，方便 Swift 侧调用。
// 设计约束（docs/plans/数学CAS工具接入.md）：
// - 不用 eval/Function：math.evaluate 是 math.js 自己的表达式解析器，只认数学表达式
// - 变量统一改名为 __cas_v：math.js 把 t 当单位（吨），不换名会误判
// - 精确值优先：整数/分数线用分数输出，只有无理数才退回小数
function __casEval(op, expr, variable, lower, upper, statOp, data) {
  function fmt(v) {
    try {
      if (typeof v === 'number' && isFinite(v)) {
        const fr = math.fraction(v);
        // mathjs 的 Fraction 用 s 存符号、n 只存绝对值，直接拼 n 会把 -2 变成 2；
        // 数值积分的 -0 也要归一成 0，否则训练/展示会出现「-0」
        if (fr && fr.d === 1n) return fr.n === 0n ? '0' : (fr.s < 0n ? '-' : '') + fr.n.toString();
        if (fr && fr.d <= 10000n) return math.format(fr);
        return math.format(v, { precision: 14 });
      }
      if (v && typeof v.toTex === 'function') return v.toString();
      return math.format(v, { precision: 14 });
    } catch (e) { return String(v); }
  }
  function bound(s, dflt) {
    if (s === null || s === undefined || String(s).length === 0) return dflt;
    const v = math.evaluate(sanitize(String(s)));
    if (typeof v !== 'number' || !isFinite(v)) throw new Error('上下限必须是数值');
    return v;
  }
  // 模型/用户常直接粘 LaTeX：\frac、e^{x}、log_2(x)、\{ \} 分组。这里做一层保守归一，
  // 只处理无歧义的写法；归一后再交给 math.js 自己的解析器（仍然不碰 eval/Function）。
  function sanitize(input) {
    let s = String(input == null ? '' : input).trim();
    s = s.replace(/^\$+|\$+$/g, '').replace(/\\left|\\right/g, '');
    s = s.replace(/\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, '(($1)/($2))');
    s = s.replace(/\\sqrt\s*\{([^{}]*)\}/g, 'sqrt($1)');
    s = s.replace(/\\cdot|\\times/g, '*');
    s = s.replace(/\\[,;!]/g, '');  // LaTeX 细间距（∫ f(x)\,dx 里的 \,）
    s = s.replace(/e\s*\^\s*\{([^{}]*)\}/g, 'exp($1)');
    s = s.replace(/\\?log\s*_\s*\{?(\d+)\}?\s*\(([^()]*)\)/g, 'log($2,$1)');
    s = s.replace(/\blog\s*_?\s*(\d+)\s*\(([^()]*)\)/g, 'log($2,$1)');
    s = s.replace(/\blog\s*_?\s*(\d+)\s+([0-9.]+)/g, 'log($2,$1)');
    s = s.replace(/(\d)\s*\\(arctan|arcsin|arccos|sin|cos|tan|exp|log|sqrt|abs)/g, '$1*$2');
    s = s.replace(/\\(arctan|arcsin|arccos)/g, '$1')
         .replace(/\b(arctan|arcsin|arccos)\b/g,
                  (m) => ({ arctan: 'atan', arcsin: 'asin', arccos: 'acos' }[m]));
    s = s.replace(/\\(sin|cos|tan|exp|log|sqrt|abs|pi|theta|phi)/g, '$1');
    // sin^2 x / \sin^2{x}：函数名后跟幂，补成 sin(x)^2（否则 math.js 把 sin 当变量）
    s = s.replace(/\b(sin|cos|tan|log|exp|sqrt|abs|asin|acos|atan)\s*\^\s*(\d+)\s*\(([^()]*)\)/g, '$1($3)^$2');
    s = s.replace(/\b(sin|cos|tan|log|exp|sqrt|abs|asin|acos|atan)\s*\^\s*(\d+)\s*\{([^{}]*)\}/g, '$1($3)^$2');
    s = s.replace(/\b(sin|cos|tan|log|exp|sqrt|abs|asin|acos|atan)\s*\^\s*(\d+)\s+([A-Za-z0-9_.^]+)/g, '$1($3)^$2');
    // sin x / arctan x 这类省括号写法补成 sin(x)
    s = s.replace(/\b(atan|asin|acos|sin|cos|tan|log|sqrt|exp|abs)\s+([A-Za-z0-9_.^]+)/g, '$1($2)');
    s = s.replace(/\{/g, '(').replace(/\}/g, ')');
    return s;
  }
  // 连除（5 / 2 / sqrt(...)）模型容易读成 5*sqrt/2；两个以上除号才全加括号，单除号保持简洁
  function fmtNode(node) {
    const s = node.toString();
    return (s.match(/\//g) || []).length > 1 ? node.toString({ parenthesis: 'all' }) : s;
  }
  // 有理函数导数先 rationalize，能化简成单一分式（-7/(x-2)^2）；遇三角函数/根式会抛错，退回 simplify
  function simplifyDerivative(node) {
    try { return math.rationalize(node); } catch (e) { return math.simplify(node); }
  }
  // 网格扫描 + 二分：覆盖多根，同时拒绝极点附近的伪变号（1/x 不会报 0）
  function findRoots(F, lo, hi) {
    const n = 4000, step = (hi - lo) / n, out = [];
    function bisect(a, b, ya) {
      let fa = ya, fb = F(b);
      if (!isFinite(fa) || !isFinite(fb)) return null;
      for (let i = 0; i < 100; i++) {
        const m = (a + b) / 2, fm = F(m);
        if (!isFinite(fm)) return null;
        if (Math.abs(fm) < 1e-10 || (b - a) < 1e-10) return Math.abs(fm) < 1e-4 ? m : null;
        if (fa * fm <= 0) { b = m; fb = fm; } else { a = m; fa = fm; }
      }
      return null;
    }
    let px = lo, py = F(lo);
    if (isFinite(py) && Math.abs(py) < 1e-10) out.push(lo);
    for (let i = 1; i <= n; i++) {
      const x = lo + i * step, y = F(x);
      if (isFinite(py) && isFinite(y) && py * y < 0) {
        const r = bisect(px, x, py);
        if (r !== null) out.push(r);
      }
      if (isFinite(y) && Math.abs(y) < 1e-10) out.push(x);
      px = x; py = y;
    }
    const ded = [];
    for (const r of out.sort((a, b) => a - b)) {
      if (!ded.length || Math.abs(r - ded[ded.length - 1]) > 1e-6 * Math.max(1, Math.abs(r))) ded.push(r);
    }
    return ded;
  }
  function numbers(s) {
    const xs = String(s || '').split(/[,;\s]+/).filter(Boolean).map(Number);
    if (!xs.length || xs.some(isNaN)) throw new Error('data 必须是逗号分隔的数字');
    return xs;
  }
  try {
    const v = variable && String(variable).length ? String(variable) : 'x';
    const VAR = '__cas_v';
    function rename(e) {
      let s = String(e);
      const names = [v];
      if (v === 'theta') names.push('θ');
      if (v === 'phi') names.push('φ');
      for (const n of names) {
        if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(n)) {
          // 不能只用 \b：隐式乘法 "5x" 里 5 和 x 之间没有词边界。
          // 用「前置字符」捕获组，避免后行断言（iOS 16.4 以下不支持 lookbehind）。
          s = s.replace(new RegExp('(^|[^A-Za-z_])' + n + '(?![A-Za-z0-9_])', 'g'), '$1' + VAR);
        } else {
          s = s.split(n).join(VAR);
        }
      }
      return s;
    }
    const restore = (s) => String(s).split(VAR).join(v).split('\\_\\_cas\\_v').join(v);
    // 变量名以 _ 开头时 mathjs 的 toTex 会输出 "5\cdot\_\_cas..."，还原后变成 "\cdotx"（非法命令）
    const fixTex = (s) => String(s).replace(/\\cdot(?=[A-Za-z0-9])/g, '\\cdot ');
    const t0 = Date.now();
    let result, latex = '', numeric = false;
    switch (op) {
      case 'eval': {
        const e2 = rename(sanitize(expr));
        if (e2.indexOf(VAR) >= 0) throw new Error('eval 需要无自由变量的数值表达式；含变量请用 derivative / solve / integrate_def');
        try {
          const value = math.evaluate(e2);
          if (typeof value === 'number' && !isFinite(value)) {
            throw new Error('结果不是有限数值（可能除以 0 或超出数值范围）');
          }
          result = fmt(value);
        } catch (err) {
          const msg = String((err && err.message) || err);
          if (/Undefined symbol|Unit in function|Cannot convert/.test(msg)) {
            throw new Error('表达式含自由变量或未知单位；eval 只算纯数值，带变量请用 derivative / solve / integrate_def');
          }
          throw err;
        }
        try { latex = math.parse(e2).toTex(); } catch (e) {}
        break;
      }
      case 'simplify': {
        // math.js 自身不化简 sin²+cos²，用自定义规则补一条基本恒等式
        const s = math.simplify(rename(sanitize(expr)),
          ['sin(n1)^2 + cos(n1)^2 -> 1', 'cos(n1)^2 + sin(n1)^2 -> 1']);
        result = restore(fmtNode(s));
        try { latex = fixTex(restore(s.toTex())); } catch (e) {}
        break;
      }
      case 'derivative': {
        const d = simplifyDerivative(math.derivative(rename(sanitize(expr)), VAR));
        result = restore(fmtNode(d));
        latex = fixTex(restore(d.toTex()));
        break;
      }
      case 'integrate_def': {
        const lo = bound(lower, 0), hi = bound(upper, 1);
        // 模型有时把积分式整段粘进来（(x^3-2x+1)\,dx），去掉尾部 dx/dt
        const body = sanitize(expr).replace(/\s*d\s*[a-zA-Z]\s*$/, '');
        const code = math.compile(rename(body));
        const f = (t) => {
          const scope = {}; scope[VAR] = t;
          const r = code.evaluate(scope);
          if (typeof r !== 'number') throw new Error('被积函数必须返回数值');
          return r;
        };
        // 复合 Simpson：n 必须偶数；20000 段在手机上毫秒级
        const n = 20000, h = (hi - lo) / n;
        let sum = f(lo) + f(hi);
        for (let i = 1; i < n; i++) sum += (i % 2 ? 4 : 2) * f(lo + i * h);
        const total = sum * h / 3;
        if (!isFinite(total)) throw new Error('积分结果不是有限数值（区间内可能有奇点）');
        result = fmt(total);
        numeric = true;
        break;
      }
      case 'integrate_indef':
        throw new Error('符号积分暂未接入（二期 nerdamer），请用 integrate_def 做数值积分');
      case 'solve': {
        const lo = bound(lower, -100), hi = bound(upper, 100);
        const parts = sanitize(expr).split('=');
        let F;
        if (parts.length === 2) {
          const l = math.compile(rename(parts[0])), r = math.compile(rename(parts[1]));
          F = (t) => { const sc = {}; sc[VAR] = t; return Number(l.evaluate(sc)) - Number(r.evaluate(sc)); };
        } else {
          const c = math.compile(rename(sanitize(expr)));
          F = (t) => { const sc = {}; sc[VAR] = t; return Number(c.evaluate(sc)); };
        }
        const roots = findRoots(F, lo, hi);
        result = roots.length ? roots.map(fmt).join(', ') : '无实根（区间内）';
        numeric = true;
        break;
      }
      case 'stats': {
        if (statOp === 'regression') {
          const pts = String(data || '').split(';').map(s => s.split(/[, ]+/).filter(Boolean).map(Number));
          if (!pts.length || pts.some(p => p.length !== 2 || p.some(isNaN))) throw new Error('回归数据格式：x1,y1;x2,y2;...');
          const n = pts.length, mx = pts.reduce((s, p) => s + p[0], 0) / n, my = pts.reduce((s, p) => s + p[1], 0) / n;
          let sxx = 0, sxy = 0, syy = 0;
          for (const [x, y] of pts) { sxx += (x - mx) ** 2; sxy += (x - mx) * (y - my); syy += (y - my) ** 2; }
          const slope = sxy / sxx, intercept = my - slope * mx, r = sxy / Math.sqrt(sxx * syy);
          result = `slope=${fmt(slope)}, intercept=${fmt(intercept)}, r=${fmt(r)}`;
          numeric = true;
          break;
        }
        const xs = numbers(data);
        switch (statOp) {
          case 'mean': result = fmt(math.mean(xs)); break;
          case 'median': result = fmt(math.median(xs)); break;
          case 'variance': result = fmt(math.variance(xs)); break;
          case 'std': result = fmt(math.std(xs)); break;
          case 'variance_pop': result = fmt(math.variance(xs, 'uncorrected')); break;
          case 'std_pop': result = fmt(math.std(xs, 'uncorrected')); break;
          case 'iqr': {
            // 中位数分半法（AP Stats 口径）；math.quantileSeq 是线性插值，口径不同
            const sorted = xs.slice().sort((a, b) => a - b);
            const half = Math.floor(sorted.length / 2);
            const lower = sorted.slice(0, half);
            const upper = sorted.length % 2 ? sorted.slice(half + 1) : sorted.slice(half);
            result = fmt(math.median(upper) - math.median(lower));
            break;
          }
          case 'sum': result = fmt(math.sum(xs)); break;
          case 'min': result = fmt(Math.min(...xs)); break;
          case 'max': result = fmt(Math.max(...xs)); break;
          case 'combination': { const [n, k] = xs; result = fmt(math.combinations(n, k)); break; }
          case 'permutation': { const [n, k] = xs; result = fmt(math.permutations(n, k)); break; }
          case 'binomial': { const [n, k, p] = xs; result = fmt(math.combinations(n, k) * p ** k * (1 - p) ** (n - k)); break; }
          case 'normalcdf': {
            if (xs.length < 3) throw new Error('normalcdf 需要 data=mu,sigma,x');
            const [mu, sigma, x] = xs;
            if (!(sigma > 0)) throw new Error('标准差必须为正');
            result = fmt(0.5 * (1 + math.erf((x - mu) / (sigma * Math.sqrt(2)))));
            break;
          }
          default: throw new Error('未知 stat_op: ' + statOp);
        }
        numeric = true;
        break;
      }
      default: throw new Error('未知 op: ' + op);
    }
    return JSON.stringify({ status: 'ok', result: String(result), latex, numeric, ms: Date.now() - t0 });
  } catch (e) {
    return JSON.stringify({ status: 'error', result: String((e && e.message) || e) });
  }
}

// 验收/自检专用：两条表达式按采样点数值对拍（判分口径同 score_math_eval.py）。
// 只给 --calc-selftest 用，不对模型暴露。
function __casCompare(actual, expected, variable, tol) {
  try {
    const eps = (tol !== null && tol !== undefined && isFinite(Number(tol))) ? Math.abs(Number(tol)) : 1e-6;
    const v = variable && String(variable).length ? String(variable) : 'x';
    const VAR = '__cas_v';
    const src = (s) => String(s).split('\\_\\_cas\\_v').join(VAR);
    const ren = (s) => {
      let t = src(s);
      if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(v)) {
        t = t.replace(new RegExp('(^|[^A-Za-z_])' + v + '(?![A-Za-z0-9_])', 'g'), '$1' + VAR);
      } else {
        t = t.split(v).join(VAR);
      }
      return t;
    };
    const ca = math.compile(ren(actual)), cb = math.compile(ren(expected));
    const pts = [0.13, -0.37, 0.71, -1.23, 1.79, -2.31, 2.87, 0];
    let ok = 0, bad = 0;
    for (const p of pts) {
      const sc = {}; sc[VAR] = p;
      let va, vb;
      try { va = ca.evaluate(sc); vb = cb.evaluate(sc); } catch (e) { continue; }
      if (typeof va !== 'number' || typeof vb !== 'number' || !isFinite(va) || !isFinite(vb)) continue;
      if (Math.abs(va - vb) <= eps + 1e-6 * Math.abs(vb)) ok++; else bad++;
    }
    return JSON.stringify({ status: 'ok', result: String(bad === 0 && ok > 0), matched: ok, mismatched: bad });
  } catch (e) {
    return JSON.stringify({ status: 'error', result: String((e && e.message) || e) });
  }
}
