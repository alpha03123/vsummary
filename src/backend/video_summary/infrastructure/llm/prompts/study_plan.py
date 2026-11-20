"""学习计划的 LLM 提示词。

`STUDY_PLAN_PROMPT_TEMPLATE`：模型决定学习顺序和每课包含哪些章节（按编号回答），并写每课
内容；代码校验分课并计算时间点。`STUDY_PLAN_COPY_PROMPT_TEMPLATE`：模型分课不合格时，
代码已经切好每一课，模型只写内容。
"""

_SESSION_COPY_RULES = (
    "- title：这一课学什么，12 字以内，不要写“第几天”。\n"
    "- goal：学完这一课应该会什么，一句话，写成能检验的能力，例如“能独立写出带参数的装饰器”。\n"
    "- focus：2 到 4 条，这一课最该看懂的点，每条一句，具体到概念或步骤。\n"
    "- practice：1 到 3 条，看完马上能做的练习或自测问题。动手类内容给动手任务，概念类内容给自测问题，"
    "不要写“复习本课内容”这种空话。后面的课需要用到前面的知识时，可以安排一道回顾前面内容的题。\n"
    "- practice_minutes：认真做完 practice 大约要几分钟，5 到 20 的整数。动手写代码、写语句的题按实际要花的时间估。\n"
)

_PLAN_COPY_RULES = (
    "- overview：两三句，说明这份计划从哪里学到哪里、学完能做什么。不要描述怎么排的课、每课多长。\n"
    "- prerequisites：开始前最好已经掌握的知识，0 到 4 条；材料本身就从零讲起的话给空数组。\n"
    "- 只依据给出的内容，不要编造视频里没有的知识点；语气平实，不要口号和鼓励语。\n"
)

STUDY_PLAN_PROMPT_TEMPLATE = (
    "请把下面的学习材料排成每天约 {daily_minutes} 分钟的学习计划，并为每一课写学习内容。只输出 JSON。\n\n"
    "材料按视频列出，每个视频下是它的章节。每个章节有编号 id 和观看分钟数 minutes（已算上暂停和回看）。"
    "视频的列出顺序可能只是导入顺序，不一定是学习顺序。\n\n"
    "分课要求：\n"
    "1. 按知识的先后关系排课：先学被后面内容用到的基础，再学用到它的内容。视频标题里的编号（如 4.1、4.2）"
    "能看出课程顺序时，按编号的顺序。\n"
    "2. 同一个视频里的章节保持原来的先后顺序。\n"
    "3. 一个视频尽量放在同一课；只有一个视频一天看不完时才按章节拆开。几个短视频可以合成一课，"
    "合在一起的内容最好主题相关。\n"
    "4. 一课的时长 = 各章节 minutes 之和 + practice_minutes。接近 {daily_minutes} 分钟即可，"
    "不必凑满，不要超过 {max_minutes} 分钟。\n"
    "5. 每个章节 id 必须出现且只出现一次；chapters 按观看顺序列出 id。\n\n"
    "每一课的内容：\n"
    + _SESSION_COPY_RULES
    + "\n整份计划：\n"
    + _PLAN_COPY_RULES
    + "\n输出 JSON 结构（sessions 按学习顺序排列）：\n"
    "{{\n"
    '  "overview": "...",\n'
    '  "prerequisites": ["..."],\n'
    '  "sessions": [\n'
    '    {{"chapters": ["v1c1", "v1c2"], "title": "...", "goal": "...", "focus": ["..."], "practice": ["..."], "practice_minutes": 10}}\n'
    "  ]\n"
    "}}\n\n"
    "学习材料：{title}\n"
    "{context}"
    "视频与章节 JSON：\n"
    "{videos_json}\n"
)

STUDY_PLAN_COPY_PROMPT_TEMPLATE = (
    "下面是一份已经按每天约 {daily_minutes} 分钟切好的学习安排，共 {session_count} 课。"
    "每课要看的片段已经定了，不要改动分课，也不要合并或拆分。watch_minutes 是这一课的观看时间。\n"
    "请为每一课写学习内容，再写整份计划的概述和前置知识，只输出 JSON。\n\n"
    "要求：\n"
    "- sessions 必须正好 {session_count} 项，index 与输入一一对应。\n"
    + _SESSION_COPY_RULES
    + _PLAN_COPY_RULES
    + "\n输出 JSON 结构：\n"
    "{{\n"
    '  "overview": "...",\n'
    '  "prerequisites": ["..."],\n'
    '  "sessions": [\n'
    '    {{"index": 1, "title": "...", "goal": "...", "focus": ["..."], "practice": ["..."], "practice_minutes": 10}}\n'
    "  ]\n"
    "}}\n\n"
    "学习材料：{title}\n"
    "{context}"
    "分课安排 JSON：\n"
    "{sessions_json}\n"
)
