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

## 2026-07-14T16:48:12+08:00 [goal_scope_correction]

- ID: `9eb18cd0-66f8-42e4-8a8e-bbeddef925e4`
- 中长期目标应按 long_term 记录，而不是 short_term；当前六项目标先统一设置三年实现期限，目标日期为 2029-07-14，后续再按情况修改。

## 2026-07-14T17:00:12+08:00 [workflow_preference]

- ID: `c25bf2dd-f7ae-4e1c-9152-89c32e918569`
- 短期目标应优先放在相应长期目标之下；如果没有合适的长期目标，则短期目标可以独立放置。周目标应服务于短期目标或长期目标，并建立相应的父子层级关系。

## 2026-07-14T23:09:33+08:00 [inconvenience]

- ID: `2405fca2-2d68-4030-baec-a4a61f157d04`
- 本次长段中文内容来自口语输入，系统路由误判为非口语并保留原文；用户要求对明显口语转写进行最小必要的断句、标点和语音噪声清理，再进入预览与确认。

## 2026-07-14T23:17:42+08:00 [inconvenience]

- ID: `20aad33b-265e-43b0-b095-ee0bae6caafa`
- 口语转写中，读音相似的中文或英文人名、公司名和物件名可能被错转写（例如 Karl/Kau 应为 Kyle）。清理阶段必须把这类可能改变实体身份的规范化列为待确认项，在预览中直接向用户澄清；不得因上下文或相似读音静默替换。

## 2026-07-16T15:30:33+08:00 [feature-request]

- ID: `bfd13a32-8e78-4d2c-8556-efdb7c60c142`
- Add first-class decisions: pending or made/archived, reusable theme tags, structured decision analysis with facts/assumptions/judgement separation, timeline-aware weekly reminders, agent-filled previews requiring confirmation, and explicit pending-to-made changes.

## 2026-07-18T23:27:14+08:00 [feature_request]

- ID: `42e99deb-430b-465b-9c27-b29f705fa40c`
- 正式启用 thought 作为与 diary 区分的一等记录类型。普通用户输入以整次输入为分类单位，只能整体归为 thought 或 diary，不按段落拆成不同记录类型；物理学、生物学、人生、哲学等属于主题或标签而不是 entry type。预览必须显示并允许在确认前纠正类型，搜索与周度回顾应能区分两类。将 D:\Project_PA\data\project_pa.db 中 user_id=2、已确认且 category=THOUGHT（大小写不敏感）的 9 条输入按原始类型、原始日期和原文迁移到本地系统，排除 testuser，并保持预览确认、去重和来源审计。完成后在仓库 README 记录用户用法、分类边界、迁移和维护方式。

## 2026-07-19T10:58:12+08:00 [workflow]

- ID: `c5cdf7f0-7970-46c4-b04d-dcf2382dd420`
- 更新 record-life-journal：当我输入一个想法后，先用100到200字给出你的看法，尽量同时包含支持与反驳，并拓展它的优点、局限及与其他密切观点、证据和我过往想法的联系。随后由我决定最终入库的是原想法、我指定的内容，还是你整理的双方观点；同时保留我要求直接入库或不入库的选择。

## 2026-07-19T11:05:45+08:00 [workflow]

- ID: `a5533aba-c804-4c33-accb-d0db291fd6aa`
- 扩充尚未批准的 thought 对话提案：为 diary、thought、decision 都增加独立且可持久化的 Agent 反馈栏目，与用户原文和 clean_text 分开。diary 的 Agent 反馈被动触发；thought 和 decision 默认主动生成分析。decision 的短反馈主要结合过去相关的 confirmed decisions 和 thoughts 给出建议，尽量同时呈现支持理由和反方/风险，并控制在 200 字内。

## 2026-07-24T09:50:12+08:00 [performance]

- ID: `82bad01e-e530-4492-934b-19fd4c750e65`
- 记日记 Skill 每次使用过慢。用户要求最大速度默认：普通 diary/thought 不加载历史正文或目标解释，thought 仅短评；weekly、decision、明确深入请求或强信号才加载深上下文。将主 SKILL.md 压缩并按步骤拆分 references，修复 create-draft 过大 JSON、重复初始化、检索先全量补查和长 JSON Errno 36；复杂清理/分类使用只读 gpt-5.6-terra low 单 worker。

