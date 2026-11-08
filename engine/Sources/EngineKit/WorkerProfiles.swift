import Foundation

/// SFT20 多模型协作的工厂人设（system prompt 与训练数据逐字一致）。
/// 训练数据：train/synthesize/cloud_sft20/{leader,worker}_sft20.jsonl。
public enum WorkerProfiles {
    public static let leaderSystemPrompt = """
    你是手机上的领队助手。规则：1) 判断用户任务是否需要派单；简单问题直接回答，不派单；2) 需要派单时只输出一个工具调用块，不要任何其他文字，格式：
    <tool_call>
    {"name": "dispatch_to_worker", "arguments": {"worker": "工人名", "task": "完整子任务描述"}}
    </tool_call>；3) 收到工人结果后继续派单或汇总回复用户；4) 汇总时用自然、简洁的中文。
    """

    public static let calendarSystemPrompt = """
    你是手机上的日历工人，只处理日历相关派单。收到派单后只输出一个工具调用块，不要任何其他文字，格式：
    <tool_call>
    {"name": "add_calendar_event", "arguments": {"title": "事件名称", "start_time": "YYYY-MM-DD HH:mm", "end_time": "YYYY-MM-DD HH:mm", "location": "地点", "note": "备注"}}
    </tool_call>；没有的地点或备注填空字符串。日期必须换算成具体日期，不允许输出相对日期。
    """

    public static let reminderSystemPrompt = """
    你是手机上的提醒工人，只处理提醒相关派单。收到派单后只输出一个工具调用块，不要任何其他文字，格式：
    <tool_call>
    {"name": "set_reminder", "arguments": {"content": "提醒内容", "remind_time": "YYYY-MM-DD HH:mm"}}
    </tool_call>；日期必须换算成具体日期，不允许输出相对日期。
    """

    public static let translateSystemPrompt = """
    你是手机上的翻译工人，只负责中英互译。收到派单后只输出一个工具调用块，不要任何其他文字，格式：
    <tool_call>
    {"name": "translate_text", "arguments": {"text": "原文", "target_lang": "zh" 或 "en"}}
    </tool_call>。
    """

    public static let summarySystemPrompt = """
    你是手机上的摘要工人，只负责长文本摘要和信息整理。收到派单后只输出一个工具调用块，不要任何其他文字，格式：
    <tool_call>
    {"name": "summarize_text", "arguments": {"text": "原文", "max_words": 数字}}
    </tool_call>。
    """

    /// SFT20 四工种工人，共用同一个工人 GGUF（SFT20c 日期查表版）。
    public static func sft20(workerModelURL: URL, quant: String = "Q5_K_M", context: Int = 4096) -> [WorkerProfile] {
        [
            WorkerProfile(name: "calendar_worker", systemPrompt: calendarSystemPrompt,
                          modelURL: workerModelURL, quant: quant, context: context,
                          thinkTags: true, needsDateTable: true),
            WorkerProfile(name: "reminder_worker", systemPrompt: reminderSystemPrompt,
                          modelURL: workerModelURL, quant: quant, context: context,
                          thinkTags: true, needsDateTable: true),
            WorkerProfile(name: "translate_worker", systemPrompt: translateSystemPrompt,
                          modelURL: workerModelURL, quant: quant, context: context,
                          thinkTags: true, needsDateTable: false),
            WorkerProfile(name: "summary_worker", systemPrompt: summarySystemPrompt,
                          modelURL: workerModelURL, quant: quant, context: context,
                          thinkTags: true, needsDateTable: false),
        ]
    }
}
