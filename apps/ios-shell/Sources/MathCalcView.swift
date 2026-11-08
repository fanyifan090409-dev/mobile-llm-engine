import SwiftUI

// CAS 一期 iOS 入口（docs/plans/数学CAS工具接入.md）：
// 输入 → CalcRouter 确定性路由 → JavaScriptCore/math.js 本机计算。
// 界面必须回显「我理解的计算」，让用户能看出是式子读错了还是算错了。
struct MathCalcView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.colorScheme) private var scheme
    @State private var input = ""
    @State private var outcome: Outcome?
    @State private var errorText: String?
    @FocusState private var focused: Bool

    // Xcode App 目标没有 SPM module bundle，math.js 在 Math/ 文件夹引用下。
    // 用 static 保证 JSContext 只建一次（View 结构体会反复创建）。
    private static let engine = MathEvalEngine(resourceDirectory: "Math")

    private let examples = [
        "1/3+1/6",
        "d/dx x^3+2*x",
        "积分 x^2 从 0 到 1",
        "解方程 x^2-5x+6=0",
        "均值: 4,8,6,10,2",
        "回归: 1,2;2,4;3,5;4,8",
    ]

    private struct Outcome {
        let request: String
        let value: String
        let numeric: Bool
        let latex: String
        let milliseconds: Int
    }

    var body: some View {
        List {
            Section {
                TextField("输入表达式或口令", text: $input, axis: .vertical)
                    .lineLimit(1...3)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .focused($focused)
                    .submitLabel(.go)
                    .onSubmit(calculate)
                Button(action: calculate) {
                    Label("计算", systemImage: "equal.square")
                }
                .disabled(input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            } footer: {
                Text("支持求值、求导、化简、定积分、解方程、统计。也可以直接写 d/dx、积分…从…到…、解方程、均值: 等口令。")
            }

            if let outcome {
                Section("结果") {
                    Text(outcome.value)
                        .font(.system(.title2, design: .rounded).weight(.semibold))
                        .textSelection(.enabled)
                    if outcome.numeric {
                        Label("数值解", systemImage: "function")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    LabeledContent("耗时", value: "\(outcome.milliseconds) ms")
                    Text("我理解的计算：\(outcome.request)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                    if !outcome.latex.isEmpty {
                        DisclosureGroup("LaTeX") {
                            Text(outcome.latex)
                                .font(.caption.monospaced())
                                .textSelection(.enabled)
                        }
                        .font(.caption)
                    }
                }
            }

            if let errorText {
                Section {
                    Label(errorText, systemImage: "exclamationmark.triangle")
                        .font(.footnote)
                        .foregroundStyle(.red)
                }
            }

            Section("示例") {
                ForEach(examples, id: \.self) { example in
                    Button {
                        input = example
                        calculate()
                    } label: {
                        HStack {
                            Text(example)
                                .font(.callout.monospaced())
                                .foregroundStyle(.primary)
                            Spacer()
                            Image(systemName: "arrow.up.left")
                                .font(.caption)
                                .foregroundStyle(.tertiary)
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }

            Section {
                Label("计算全部在本机完成，不需要模型、不联网。", systemImage: "lock.shield")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .scrollContentBackground(.hidden)
        .background(
            LinearGradient(
                colors: scheme == .light
                    ? [Color(red: 0.88, green: 0.90, blue: 0.96), Color(red: 0.96, green: 0.97, blue: 0.99)]
                    : [Color(red: 0.05, green: 0.05, blue: 0.08), Color(red: 0.11, green: 0.11, blue: 0.15)],
                startPoint: .top, endPoint: .bottom)
            .ignoresSafeArea())
        .navigationTitle("数学计算")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button("完成") { dismiss() }
            }
        }
    }

    private func calculate() {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        focused = false
        let request = CalcRouter.route(text)
        if request.op == "stats" && request.statOp.isEmpty {
            outcome = nil
            errorText = "统计计算需要在开头写清楚统计量，例如「均值: 1,2,3」。"
            return
        }
        if request.op != "stats" && request.expr.isEmpty {
            outcome = nil
            errorText = "没有识别到表达式。"
            return
        }
        do {
            let output = try Self.engine.run(
                op: request.op,
                expr: request.expr,
                variable: request.variable,
                lower: request.lower,
                upper: request.upper,
                statOp: request.statOp,
                data: request.data)
            outcome = Outcome(request: request.describe, value: output.result,
                              numeric: output.numeric, latex: output.latex,
                              milliseconds: output.milliseconds)
            errorText = nil
        } catch {
            outcome = nil
            errorText = (error as? LocalizedError)?.errorDescription ?? "\(error)"
        }
    }
}
