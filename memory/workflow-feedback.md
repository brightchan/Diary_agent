# Workflow Feedback

## 2026-07-13T21:29:01+08:00 [feature_request]

- ID: `1e9520ea-bbba-4bd8-861f-50caad7dc3b6`
- 希望在每周总结中加入主题整理流程：审视已有主题，提出合并、拆分、重命名或保留建议，并在用户确认后才应用；同时增加长期记忆，记录人生目标、短期目标和周目标，并用这些目标作为日记回顾与后续对话的指导上下文。

## 2026-07-13T21:34:24+08:00 [feature_request]

- ID: `6e4005de-5bc3-445d-b956-4986fcf15a7f`
- 将主题正式建模为文章 Tag：允许给已确认文章追加新的主题链接；维护 active/inactive 主题状态。Inactive 主题及其历史文章关联继续保存在数据库和文章标签中，但不再用于新文章分类候选、主题筛选或主题驱动的检索；Active 主题列表由数据库状态实时生成，避免维护独立且可能失同步的列表。周度主题整理应提出新增标签、启用、停用、合并或拆分建议，并在用户逐项确认后应用。

## 2026-07-13T21:37:13+08:00 [design_preference]

- ID: `8e485105-2361-4c7e-b211-bc8e11ab3c94`
- 用户确认现有一个 segment 对应一个主题 Tag 的模型可以接受，不需要另建文章级 Tag 体系。Active/Inactive 应继续作为 themes 的全局状态；如增加新表，应用于周度主题变更提案与审计历史，而不是建立重复的 entry_themes 分类层。

## 2026-07-14T08:21:41+08:00 [feature-request]

- ID: `4e11eda9-68bc-447c-b984-75ede930ebb1`
- Allow unqualified personal sentences to trigger the diary capture skill without requiring an explicit record command; allow one segment to carry multiple searchable tags; retrieve relevant older diary segments for weekly reviews and optional evidence-based prompts, while remaining local-first and avoiding external model/API dependencies.

## 2026-07-14T12:47:25+08:00 [new_need]

- ID: `dd9a1448-cb9c-4895-94c9-2cd26e9ea09f`
- Automatically match every diary entry against relevant active goals during the normal capture flow and provide concise goal-related feedback without an extra interaction. Preserve the cleaned journal as the user's wording, append a clearly labeled AI goal interpretation section to the preview and confirmed cleaned Markdown, and make the structured interpretations available to weekly review. The user should be able to correct or remove the interpretation before confirming the entry.

## 2026-07-14T13:09:59+08:00 [workflow_preference]

- ID: `806ac4cd-9c4d-400f-9c52-2dbe3233f61b`
- After every weekly review generation or implementation of a workflow revision, commit the complete repository state and push the current branch so no generated or implemented changes remain only local.

## 2026-07-14T15:50:48+08:00 [workflow_preference]

- ID: `c1d84396-8e5a-4cc5-957c-eeee9034f8ad`
- 如果输入内容口语化不明显，应减少清洗和修改，尽量按原文记录；并应定期根据原始输入归纳清洗语言风格，使清洗结果保留我的文风和语言习惯。

## 2026-07-14T16:17:10+08:00 [feature_request]

- ID: `fa49726d-d2b1-4cff-8114-472dfeffc9b9`
- 目标分类需要新增 long_term：long-term 目标以年为时间单位；short_term 目标应在一年内完成。保留 life 与 weekly，并让目标层级和文档明确支持 life -> long_term -> short_term -> weekly。

