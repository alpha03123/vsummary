"""AI 视频笔记提示词与风格预设。

设计取向（参考 BiliNote 的笔记提示词）：以「写全、写细、好读」为主，
少用劝退式限制（例如"仅在确有助益时才保留"），只保留必要的输出格式
约定与反臆造要求，避免模型因约束过多而只产出骨架。
"""

from __future__ import annotations


# 笔记风格预设：`label` 为界面展示名，`instruction` 为该风格的写作侧重。
# key 是对外契约值（见 `api.schemas.contracts.AiNoteTemplate`），不要随意改动。
NOTE_TEMPLATES: dict[str, dict[str, str]] = {
    "general": {
        "label": "通用笔记",
        "instruction": (
            "结构清晰、重点突出：按视频自身的脉络分章节，"
            "每个主题写清在讨论什么、得出的结论是什么，并保留必要的细节和例子，便于日后复习。"
        ),
    },
    "minimal": {
        "label": "要点速览",
        "instruction": "只保留结论、关键事实和必要步骤，紧凑到可以一眼扫完。",
    },
    "detailed": {
        "label": "深度详记",
        "instruction": "完整覆盖每个主题的论述、例子和步骤，不遗漏关键内容。",
    },
    "tutorial": {
        "label": "操作教程",
        "instruction": "按操作顺序整理，写清前提、步骤、关键点、结果和容易踩坑的边界。",
    },
    "academic": {
        "label": "学术论文",
        "instruction": "用正式、客观的表达，清晰区分概念、论据、方法和结论。",
    },
    "life_journal": {
        "label": "生活随笔",
        "instruction": "以自然亲切的口吻记录经历、感受和可借鉴的做法，但不添加视频之外的感受。",
    },
    "task_oriented": {
        "label": "任务清单",
        "instruction": "突出问题、待办、决策、负责人和下一步；没有依据时不要虚构责任人或时间。",
    },
    "meeting_minutes": {
        "label": "会议纪要",
        "instruction": "按议题梳理讨论、结论、待办和待确认事项；没有依据时不要补写负责人或截止时间。",
    },
}

DEFAULT_NOTE_TEMPLATE = "general"


def build_ai_note_prompt(
    *,
    title: str,
    transcript_text: str,
    template: str = DEFAULT_NOTE_TEMPLATE,
    summary_text: str = "",
    outline_text: str = "",
) -> str:
    """构建直接生成 AI 笔记时使用的提示词。

    Args:
        title: 视频标题。
        transcript_text: 已按「时间 - 内容」拼好的转写全文。
        template: 笔记风格 key，未知 key 回退到通用。
        summary_text: 可选的整体概况，仅作辅助参考。
        outline_text: 可选参考大纲（通常来自已有概况的章节标题与起始时间），
            用于让笔记沿用既有章节结构并获得准确时间点。

    Returns:
        可直接作为单轮 user 消息发送的提示词文本。
    """
    resolved_template = NOTE_TEMPLATES.get(template, NOTE_TEMPLATES[DEFAULT_NOTE_TEMPLATE])
    summary_section = (
        f"\n已有概况（仅作辅助，仍以转写为准）：\n{summary_text.strip()}\n" if summary_text.strip() else ""
    )
    outline_section = (
        "\n参考大纲（来自该视频已有的概况）：\n"
        f"{outline_text.strip()}\n"
        "章节划分可以参考它，大纲没覆盖到的内容另起章节补充，不要遗漏；"
        "单纯致谢、求关注一类的片尾章节可以省略。\n"
        if outline_text.strip()
        else ""
    )
    return (
        "你是专业的视频笔记助手，擅长把视频转写整理成内容完整、条理清晰、可以直接复习的 Markdown 笔记。\n"
        "语言：笔记用中文撰写；专有名词、技术术语、品牌名和人名保留原文（通常是英文），不要硬译。\n\n"
        f"视频标题：{title}\n"
        f"笔记风格：{resolved_template['label']}。{resolved_template['instruction']}\n\n"
        "写作要求：\n"
        "1. 记录全面：视频讲到的实质内容都写进笔记，包括观点、论证、细节、例子、数据和结论；不要只留骨架。\n"
        "2. 保留关键细节：重要事实、数字、术语、例子和问答都保留；术语首次出现时给出原文叫法；公式用 LaTeX 表达。\n"
        "3. 去掉无关内容：寒暄、广告、片头片尾和订阅引导不必写进笔记。\n"
        "4. 表达与结构：尽量用书面、完整的表达，避免口语碎句；用标题和列表组织，标题概括这一节的结论；"
        "节内用 `**要点**：说明` 的加粗小标题分组，比一长串平行列表更好扫读；"
        "作者的精彩表述用 `>` 引用块原样保留。\n"
        "5. 收尾可以补一节「可以用在哪」，基于视频内容给出适用场景和可迁移做法，不要引出视频之外的新事实。\n"
        "6. 不要去讨论转写本身的问题（比如听不清、未可确证、原文如此）；术语听不准就用最可能的写法，"
        "但产品名和工具名听不准时改用通称（例如「AI 知识库工具」），不要列举视频没有提到的具体产品。\n"
        "7. 以视频为准，不要编造。\n\n"
        "输出要求：\n"
        "- 第一行用一级标题给这篇笔记起名，格式 `# 标题`：概括视频主题、不超过 20 字，"
        "不要照抄视频标题，不要用感叹号、营销词或活动标签。\n"
        "- 只输出最终 Markdown 正文，不要用代码块包裹，也不要加开场白或结束语。\n"
        "- 编号标题统一写成 `## 1. 标题`；如需加粗编号，写成 `1\\. **内容**`，避免被渲染成有序列表。\n"
        f"{summary_section}{outline_section}\n视频转写（格式：时间 - 内容）：\n---\n{transcript_text.strip()}\n---"
    )
