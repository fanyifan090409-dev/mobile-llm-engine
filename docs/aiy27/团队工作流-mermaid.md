# 团队工作流（Mermaid 版）

> 同一个工作流的两张代码图。GitHub 的 `.md` 预览会直接渲染；VS Code 需要装 *Markdown Preview Mermaid Support*；也可以整段粘到 [mermaid.live](https://mermaid.live)。
> 优点：纯文本，可 diff、可评审、随仓库走。缺点：样式由渲染器决定，和 PPT 视觉不统一。
> 不想开 GitHub 也能看：[渲染预览图](figures/mermaid/工作流-mermaid-预览.png)。

## 一、分工与流转

```mermaid
flowchart LR
    S["共用一份<br/>《智能体协作守则》"]

    L["队长 · 樊一凡<br/>智能体：代码 / 调试 / 文档<br/>人：架构 / 评审 / 合并"]
    A["张曜阳 · 质量<br/>智能体：整理卡点记录<br/>人：首装走查 / 记录卡点"]
    B["薛亦湘 · 用户验证<br/>智能体：整理访谈记录<br/>人：组织试用 / 核对数字"]

    I["Issue 任务单<br/>目标 / 验收 / 证据"]
    BR["独立分支<br/>一人一支"]
    PR["提交 PR<br/>截图 / 原话 / 来源"]
    RV["队长评审<br/>逐条对验收"]
    MG["合并 main<br/>PR 编号进记录"]

    S -.-> L
    S -.-> A
    S -.-> B

    L --> I
    I --> A
    I --> B
    A --> BR
    B --> BR
    BR --> PR
    PR --> RV
    RV -->|批准| MG
    RV -.->|打回补证据| PR

    classDef role fill:#EAF1FF,stroke:#1E6BFF,color:#123A7A
    classDef pipe fill:#FFFFFF,stroke:#8C959F,color:#24292F
    classDef shared fill:#F6F8FA,stroke:#9AA0A6,color:#3C4043,stroke-dasharray:4 3
    classDef done fill:#E6F4EA,stroke:#2DA44E,color:#116329
    class L,A,B role
    class I,BR,PR,RV pipe
    class S shared
    class MG done
```

## 二、一件任务的生命周期

```mermaid
sequenceDiagram
    autonumber
    participant L as 队长
    participant GH as GitHub
    participant A as 队员 + 智能体

    L->>GH: 开 Issue（目标 / 交付路径 / 验收 / 证据）
    GH-->>A: 认领任务
    A->>A: 智能体列执行清单
    A->>A: 本人实测，产生截图与原话
    A->>GH: 建分支 → 提交 PR（附证据、AI 参与说明）
    GH->>L: 请求评审
    alt 验收不通过
        L->>A: 打回，写清缺哪条证据
        A->>GH: 补证据后重新提交
    else 验收通过
        L->>GH: 合并 main
        GH-->>L: PR 编号写进协作记录
    end
```

## 三、和网页版的分工

| | Mermaid 版（本文件） | 网页版 `团队工作流.html` |
|---|---|---|
| 载体 | 纯文本，进仓库 | 单文件 HTML |
| 渲染 | GitHub / mermaid.live | 浏览器直接打开 |
| 视觉 | 渲染器默认，开发文档风 | 与 PPT v6 同一套深蓝 |
| 改动 | 改文字，diff 可评审 | 改 HTML |
| 适用 | 仓库内文档、评审、留档 | 答辩展示、PPT 插图 |