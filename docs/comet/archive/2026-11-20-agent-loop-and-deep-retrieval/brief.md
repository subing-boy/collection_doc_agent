# 目标

1. 优化混合检索文档匹配规则（`storage/vector_store.py`）：
   - 解决短语子词重叠导致的关键词分数虚高与过早饱和问题（存在复合短语时不重复累计单子词）；
   - 引入罕见词/专业术语优先加权机制，对库内低频特定词（如 `vad`）赋予核心高权重；
   - 引入多概念交集覆盖率（Concept Coverage & Intersection Bonus）：切片同时命中不同概念（如 `live mode` 场景与 `vad` 主体）时获得置顶加成，保证复合专业问题精准命中。
2. 构建最多 4 轮的自主纠错 Agent Loop 机制与深度筛查工具集（`core/agent_core.py`）：
   - 建立有限硬编码计数器（`MAX_AGENT_LOOPS = 4`），配备工具去重锁、请求超时与本地毫秒执行防线，彻底杜绝死循环卡死；
   - 质量门禁：检查召回切片中核心专有名词的覆盖完整度及大模型反馈；
   - 装备深度筛查工具：`deep_keyword_grep`（全库穿透定位特定关键词切片）、`expand_adjacent_chunks`（自动抓取前后关联上下文）；
   - 整合多轮检索证据交付 LLM 综合输出详尽规范的需求文档。
3. 维测轨迹记录：在 `agent_debug.txt` 完整透明记录多轮循环中每一轮的 Thought、工具调用与证据补充过程。

# 范围

## 目录结构

### 修改
- `storage/vector_store.py`: 优化检索打分算法，增加概念去重、罕见词加权与多概念交集奖励。
- `storage/metadata_db.py`: 新增 `grep_chunks_by_term` 与 `get_adjacent_chunks` 深度筛查与上下文扩展接口。
- `core/query_optimizer.py`: 完善实体覆盖度核验与未命中指示词识别。
- `core/agent_core.py`: 重构 `ask()`，引入 4 轮上限的 Agent Loop 调度流、工具调用与多轮维测轨迹记录。
- `tests/test_skeleton.py`: 新增针对 `live mode 中 vad 具体实现` 的检索优化与 Agent Loop 自愈机制自动化测试用例。

### 明确不建
- 严禁使用无限循环 `while True`，严格锁定上限 4 轮。
- 严禁重复无意义地调用相同工具，避免产生死锁或死循环。

# 非目标

- 正常单轮高置信度命中的简单问题保持 1 轮极速输出，不引入多余轮次开销。
- 不影响 Word、PPT、Excel、MSG 等多格式正常解析入库。

# 验收示例

- 输入提问 `live mode 中 vad  具体实现请写出一个具体的需求文档`，系统不再返回“未找到”，而是精准锁定 `Live_Mode_Device_Design_ODM_V1.0.md` 第 8 节（含 Phase 1 与 Phase 2）并生成详尽需求文档。
- Agent Loop 具备多轮调度能力，循环次数严格受控在最多 4 轮以内，绝对无卡死或挂起。
- 维测日志 `agent_debug.txt` 清晰呈现多轮循环中的交互轨迹、工具调用与切片补充记录。
- 全套端到端自动化测试套件继续 100% 通过，沙箱自动销毁无残留。
