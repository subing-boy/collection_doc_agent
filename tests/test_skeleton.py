"""
==============================================================================
模块名称: tests/test_skeleton.py
功能描述: 个人文档管家 Agent 核心骨架端到端全链路自检脚本
          特点：
          1. 采用隔离沙箱机制 (Sandbox)，所有自测产生的数据库、分类文件、生成物
             均限定在 data/test_sandbox/ 临时目录下运行；
          2. 测试完成后自动执行完整清理，确保 data/ 生产目录 100% 保持纯净无残留；
          3. 验证涵盖：PPTX/DOCX 解析切片、分类物理搬运、SQLite/向量存储持久化、
             带出处精准问答、记忆/重试骨架、Word/PPT 逆向生成导出。
==============================================================================
"""

import sys
import shutil
from pathlib import Path

# 将项目根目录添加进 sys.path，保证随处可执行
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pptx
from pptx.util import Inches, Pt
import docx

import config
from storage.metadata_db import MetadataDB
from storage.vector_store import EmbeddedVectorStore
from core.agent_core import AgentCore


def create_sample_files(temp_dir: Path) -> tuple[Path, Path]:
    """在测试沙箱内动态生成用于测试的样例 PPTX 和 DOCX"""
    temp_dir.mkdir(parents=True, exist_ok=True)
    ppt_path = temp_dir / "个人文档管家架构设计.pptx"
    doc_path = temp_dir / "知识检索与问答技术规范.docx"

    # --- 1. 创建样例 PPTX ---
    prs = pptx.Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # 幻灯片 1: 封面
    title_slide_layout = prs.slide_layouts[0]
    slide1 = prs.slides.add_slide(title_slide_layout)
    slide1.shapes.title.text = "个人文档管家核心架构"
    slide1.placeholders[1].text = "基于 DeepSeek 与本地向量引擎的端到端方案"

    # 幻灯片 2: 方案细节 (含表格与演讲者备注)
    blank_layout = prs.slide_layouts[6]
    slide2 = prs.slides.add_slide(blank_layout)
    tx = slide2.shapes.add_textbox(Inches(1.0), Inches(0.8), Inches(11.0), Inches(1.0))
    tx.text_frame.text = "精密切片与出处定位机制"

    tx_body = slide2.shapes.add_textbox(Inches(1.0), Inches(2.0), Inches(6.0), Inches(4.5))
    tf = tx_body.text_frame
    p1 = tf.paragraphs[0]
    p1.text = "PPT 切片规则：严格以 1 Slide 为 1 个原子知识切片"
    p2 = tf.add_paragraph()
    p2.text = "切片元数据包含页码、标题、正文、表格与演讲者备注"

    table_shape = slide2.shapes.add_table(2, 2, Inches(7.5), Inches(2.0), Inches(4.5), Inches(2.0))
    table = table_shape.table
    table.cell(0, 0).text = "特性"
    table.cell(0, 1).text = "参数指标"
    table.cell(1, 0).text = "端到端检索延迟"
    table.cell(1, 1).text = "小于 10 毫秒"

    slide2.notes_slide.notes_text_frame.text = "请向评审专家着重强调我们的 1 Slide 对应 1 Chunk 出处策略。"
    prs.save(str(ppt_path))

    # --- 2. 创建样例 DOCX ---
    doc = docx.Document()
    doc.add_heading("知识检索与问答技术规范", level=0)
    
    doc.add_heading("1. 溯源问答设计原则", level=1)
    doc.add_paragraph("在针对文档库进行大模型问答时，每一个给出的论据必须包含精准出处。")
    doc.add_paragraph("如果材料中不存在答案，大模型必须明确回答未找到相关信息，严禁幻觉编造。")

    doc.add_heading("1.1 记忆管理与滑动窗口", level=2)
    doc.add_paragraph("系统具备记忆压缩管理器，当对话轮数超过阈值时触发摘要降维，保证长会话低开销。")

    doc.add_heading("3. 5.21 AI Chat (0x21) 协议定义", level=1)
    doc.add_paragraph("AI Chat 核心交互规范与语音通道，包含 AppStartChatReq 等控制指令。")

    doc.add_heading("3.1 3.2 L2CAP COC 传输通道配置", level=2)
    doc.add_paragraph("L2CAP COC 数据分包机制与 MTU 协商策略，用于高带宽语音流的高效传输。")
    doc.save(str(doc_path))

    return ppt_path, doc_path


def run_all_tests():
    """执行全部端到端功能自检，并在执行完毕后自动销毁沙箱环境"""
    print("=" * 65)
    print("🚀 开始执行『个人文档管家 Agent』核心功能全链路自检 (沙箱隔离模式)")
    print("=" * 65)

    # 1. 建立隔离沙箱路径 (不污染真实生产目录)
    sandbox_dir = config.DATA_DIR / "test_sandbox"
    sandbox_storage = sandbox_dir / "storage"
    sandbox_output = sandbox_dir / "output"
    sandbox_db_file = sandbox_dir / "test_metadata.db"
    sandbox_temp = sandbox_dir / "tmp"

    if sandbox_dir.exists():
        shutil.rmtree(sandbox_dir)
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 生成输入样例文件
        ppt_file, doc_file = create_sample_files(sandbox_temp)
        print(f"✔ 成功在沙箱生成自测样本: \n  • {ppt_file.name}\n  • {doc_file.name}")

        # 使用沙箱独立的数据库与向量存储
        test_db = MetadataDB(db_path=sandbox_db_file)
        test_vector_store = EmbeddedVectorStore(metadata_db=test_db)
        
        agent = AgentCore(
            metadata_db=test_db,
            vector_store=test_vector_store,
            storage_dir=sandbox_storage,
            output_dir=sandbox_output
        )

        # --- 测试项 1: PPTX 上传与分类归档 ---
        print("\n[测试 1/5] 执行 PPTX 文档入库与切片分类...")
        ppt_report = agent.ingest_document(ppt_file)
        assert ppt_report["status"] == "success"
        assert ppt_report["chunks_count"] == 2
        assert Path(ppt_report["stored_path"]).is_file()
        print(f"  ✔ PPTX 归档成功: 分类为 [{ppt_report['category']}], 切片数: {ppt_report['chunks_count']}")
        print(f"  ✔ 沙箱物理路径: {ppt_report['stored_path']}")

        # --- 测试项 2: DOCX 上传与分类归档 ---
        print("\n[测试 2/5] 执行 DOCX 文档入库与切片分类...")
        doc_report = agent.ingest_document(doc_file)
        assert doc_report["status"] == "success"
        assert doc_report["chunks_count"] >= 2
        assert Path(doc_report["stored_path"]).is_file()
        print(f"  ✔ DOCX 归档成功: 分类为 [{doc_report['category']}], 切片数: {doc_report['chunks_count']}")
        print(f"  ✔ 沙箱物理路径: {doc_report['stored_path']}")

        # --- 测试项 3: 向量检索与精准出处溯源 ---
        print("\n[测试 3/5] 执行知识检索与出处溯源测试...")
        query = "请问 PPT 切片规则是什么？"
        qa_res = agent.ask(query)
        assert len(qa_res["sources"]) > 0
        top_source = qa_res["sources"][0]
        print(f"  ✔ 命中相关切片: 来源文件 -> {top_source['source_filename']}")
        print(f"  ✔ 精准坐标定位: {top_source['location_label']}")
        print(f"  ✔ 相似度得分: {top_source['score']}")
        assert "个人文档管家架构设计.pptx" in top_source["source_filename"]
        assert "第2页" in top_source["location_label"]

        # --- 测试项 4: 记忆与重试模块骨架测试 ---
        print("\n[测试 4/5] 执行记忆压缩与问题优化骨架测试...")
        session_id = "test_user_session"
        agent.memory_manager.add_message(session_id, "user", "你好")
        agent.memory_manager.add_message(session_id, "assistant", "你好，我是文档管家")
        msgs = agent.memory_manager.get_messages(session_id)
        assert len(msgs) == 2
        assert not agent.query_optimizer.should_trigger_retry(qa_res["sources"])
        print(f"  ✔ 记忆会话消息入栈与读取正常 (当前消息数: {len(msgs)})")
        print(f"  ✔ 问题重试质量校验与拦截逻辑就绪")

        # --- 测试项 5: 逆向生成 Word 报告与 16:9 PPT ---
        print("\n[测试 5/6] 执行文档与演示文稿逆向生成测试...")
        generated_doc = agent.generate_new_doc(topic="架构设计总结报告")
        assert generated_doc.is_file()
        print(f"  ✔ 成功导出 Word 文档: {generated_doc.name} (大小: {generated_doc.stat().st_size} 字节)")

        generated_ppt = agent.generate_new_ppt(topic="项目架构全景汇报")
        assert generated_ppt.is_file()
        print(f"  ✔ 成功导出 16:9 商业 PPT: {generated_ppt.name} (大小: {generated_ppt.stat().st_size} 字节)")

        # --- 测试项 6: 实体探测与口语化意图提取测试 ---
        print("\n[测试 6/7] 执行长句实体提取与口语化意图探测测试...")
        from main import extract_file_path_from_text
        # 用例 A: 中文紧挨路径无空格
        extracted_a = extract_file_path_from_text(f"存下来{ppt_file}")
        assert extracted_a is not None and extracted_a.name == ppt_file.name
        # 用例 B: 带有修饰长句与末尾语气词
        extracted_b = extract_file_path_from_text(f"帮我把 {doc_file} 归档整理一下，谢谢！")
        assert extracted_b is not None and extracted_b.name == doc_file.name
        # 用例 C: 提问防误杀 (句中不含真实实体文件)
        extracted_c = extract_file_path_from_text("为什么要存下来这个文档？")
        assert extracted_c is None
        print("  ✔ 无空格紧挨指令提取正常 (如: 存下来D:\\...)")
        print("  ✔ 夹带修饰短语长句提取正常 (如: 帮我把 D:\\... 归档整理一下)")
        print("  ✔ 纯提问语句防误拦截校验正常 (如: 为什么要存下来？ -> 未误杀)")

        # --- 测试项 7: 四象限防重复入库与版本就地迭代测试 ---
        print("\n[测试 7/7] 执行四象限防重复入库与版本就地迭代测试...")
        # 1. 象限 1 测试: 同名且同内容 -> 秒级跳过
        dup_report = agent.ingest_document(ppt_file)
        assert dup_report["status"] == "skipped_duplicate"
        assert dup_report["chunks_count"] == 0
        print("  ✔ [象限1-完全重复] 同名同内容再次提交已被秒级拦截，切片未冗余增加")

        # 2. 象限 3 测试: 异名但同内容 (改名副本) -> 别名绑定
        alias_file = sandbox_temp / "个人文档管家架构设计_副本.pptx"
        shutil.copy2(str(ppt_file), str(alias_file))
        alias_report = agent.ingest_document(alias_file)
        assert alias_report["status"] == "aliased_duplicate"
        assert alias_report["chunks_count"] == 0
        assert any("别名:个人文档管家架构设计_副本.pptx" in tag for tag in alias_report["tags"])
        print("  ✔ [象限3-改名副本] 成功识别内容一致并自动建立文件名别名映射，未产生重复切片")

        # 3. 象限 2 测试: 同名但内容修改 -> 版本就地升级
        mod_doc = docx.Document(str(doc_file))
        mod_doc.add_heading("2. 新增的第二代版本规范", level=1)
        mod_doc.add_paragraph("这是同名文件升级后新增的最新核心规范，旧规范切片应被级联清理。")
        mod_doc.save(str(doc_file))

        update_report = agent.ingest_document(doc_file)
        assert update_report["status"] == "updated_version"
        assert update_report["chunks_count"] >= 3
        # 检查向量库中是否成功检索到了新版本的独有内容
        q_new = agent.ask("新增的第二代版本规范内容是什么？")
        assert any("新增的第二代版本规范" in s["location_label"] or "新增的第二代版本规范" in s["preview"] for s in q_new["sources"])
        print("  ✔ [象限2-版本迭代] 同名内容变更成功触发就地升级，旧切片级联清除，新切片即刻生效")

        # --- 测试项 8: 提问噪音词清洗与双路混合检索精准匹配测试 ---
        print("\n[测试 8/8] 执行提问噪音词清洗与双路混合检索精准匹配测试...")
        # 测试 A: 停用词清洗与专有名词提取
        cq, kws = agent.clean_query_and_extract_keywords("知识库中寻找和ai chat相关的内容")
        assert cq == "ai chat"
        assert "ai chat" in kws
        print("  ✔ 提问噪音剥离与核心关键词提取正常 (知识库中寻找... -> ai chat)")

        # 测试 B: 长句口语提问精准召回核心切片 (Top 1 必须命中 AI Chat)
        hybrid_res = agent.ask("知识库中寻找和ai chat相关的内容")
        assert len(hybrid_res["sources"]) > 0
        top_source = hybrid_res["sources"][0]
        assert "AI Chat" in top_source["location_label"] or "AI Chat" in top_source["preview"]
        print(f"  ✔ 混合检索精准将目标专有名词推至 Top 1: [{top_source['location_label']}] (得分: {top_source['score']})")

        # 测试 C: 另一组英文专有名词与中文结合长句测试
        hybrid_res_coc = agent.ask("帮我查一下L2CAP COC协议的具体数据分包逻辑")
        assert len(hybrid_res_coc["sources"]) > 0
        top_coc = hybrid_res_coc["sources"][0]
        assert "L2CAP COC" in top_coc["location_label"] or "L2CAP COC" in top_coc["preview"]
        print(f"  ✔ L2CAP COC 专有名词长句精准命中 Top 1: [{top_coc['location_label']}] (得分: {top_coc['score']})")

        # --- 测试项 9: 维测轨迹记录与自动滚动清理测试 ---
        print("\n[测试 9/9] 执行维测轨迹全要素记录与自动滚动清理测试...")
        from core.trace_logger import HarnessTraceLogger, HarnessTraceContext

        # 测试 A: 维测关闭时 0 I/O
        disabled_log = sandbox_dir / "disabled_trace.txt"
        disabled_logger = HarnessTraceLogger(enabled=False, log_file=disabled_log)
        dummy_trace = HarnessTraceContext(query="ping")
        disabled_logger.record_trace(dummy_trace)
        assert not disabled_log.exists()
        print("  ✔ 维测开关关闭时保持 0 磁盘 I/O (未生成任何日志文件)")

        # 测试 B: 维测开启时六大要素完整记录
        enabled_log = sandbox_dir / "test_trace.txt"
        enabled_logger = HarnessTraceLogger(enabled=True, log_file=enabled_log, max_mb=10, backup_count=2)
        full_trace = HarnessTraceContext(
            query="测试提问",
            session_id="test_session",
            system_prompt="测试系统提示词",
            history_dialog=[{"role": "user", "content": "前序提问"}, {"role": "assistant", "content": "前序回答"}],
            available_tools=["ToolA", "ToolB"],
            invoked_tools=[{"tool": "HybridSearch", "keywords": ["test"], "retrieved_chunks": [{"source_filename": "f.docx", "location_label": "p1", "score": 0.9}]}],
            current_prompt="测试Payload",
            llm_config={"model": "deepseek-chat", "temperature": 0.3},
            ai_response="测试自然语言回答",
            execution_time_ms=12.5
        )
        enabled_logger.record_trace(full_trace)
        assert enabled_log.is_file()
        log_content = enabled_log.read_text(encoding="utf-8")
        assert "【1. SYSTEM PROMPT (系统指令)】" in log_content
        assert "【2. 历史对话记录 (HISTORY DIALOG)】" in log_content
        assert "【3. 可用工具列表 (AVAILABLE TOOLS)】" in log_content
        assert "【4. 本轮实际调用的工具与结果 (INVOKED TOOLS & RETRIEVAL)】" in log_content
        assert "【5. 当前发给 LLM 的最终 PROMPT (CURRENT TURN PROMPT)】" in log_content
        assert "【6. AI 最终返回的自然语言回答 (AI RESPONSE)】" in log_content
        print("  ✔ 维测全要素日志生成正常，六大核心维度信息完整覆盖")

        # 测试 C: 滚动清理与最多保留 2 份备份机制
        small_log = sandbox_dir / "rotating_test.txt"
        import logging
        from logging.handlers import RotatingFileHandler
        rot_handler = RotatingFileHandler(str(small_log), maxBytes=500, backupCount=2, encoding="utf-8")
        test_rot_logger = logging.getLogger("TestRotLogger")
        test_rot_logger.setLevel(logging.INFO)
        test_rot_logger.addHandler(rot_handler)
        for i in range(20):
            test_rot_logger.info("A" * 150 + f" line {i}")
        rot_handler.close()
        test_rot_logger.removeHandler(rot_handler)

        assert small_log.exists()
        assert Path(str(small_log) + ".1").exists()
        assert Path(str(small_log) + ".2").exists()
        assert not Path(str(small_log) + ".3").exists()  # 严格不超过 2 份备份
        print("  ✔ 自动滚动切分生效，历史备份数量严格控制在设定上限内，老日志自动淘汰")

        # --- 测试项 10: Excel 表格与 Outlook 邮件多格式入库与精准溯源测试 ---
        print("\n[测试 10/10] 执行 Excel 表格与 Outlook 邮件多格式入库与溯源测试...")
        import openpyxl
        from unittest.mock import MagicMock, patch

        # 1. 动态生成测试用 Excel 文件
        excel_path = sandbox_temp / "2026年研发项目预算表.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "成本明细表"
        ws.append(["项目名称", "负责人", "预算额度", "关键指标"])
        ws.append(["文档管家Agent", "张三", "50万", "带出处RAG溯源"])
        ws.append(["音视频传输系统", "李四", "35万", "L2CAP数据分包"])
        wb.save(str(excel_path))

        excel_report = agent.ingest_document(excel_path)
        assert excel_report["status"] == "success"
        assert excel_report["chunks_count"] >= 1
        print(f"  ✔ Excel 入库成功: 分类为 [{excel_report['category']}], 切片数: {excel_report['chunks_count']}")

        # 提问 Excel 内容，验证出处包含 Sheet 与行号
        excel_qa = agent.ask("文档管家Agent的预算额度是多少？")
        assert len(excel_qa["sources"]) > 0
        top_excel_source = excel_qa["sources"][0]
        assert "成本明细表" in top_excel_source["location_label"]
        print(f"  ✔ Excel 问答精准溯源至工作表与行号: [{top_excel_source['location_label']}] (得分: {top_excel_source['score']})")

        # 2. 动态生成测试用 MSG 邮件并模拟解析
        msg_path = sandbox_temp / "关于AIW协议终审的决议.msg"
        msg_path.touch()

        mock_email = MagicMock()
        mock_email.subject = "关于AIW协议终审的决议"
        mock_email.sender = "王总 <wang@company.com>"
        mock_email.to = "项目组全体"
        mock_email.date = "2026-11-18 10:00:00"
        mock_email.body = "经评审委员会讨论，正式确认AIW 11.3协议基线标准通过。"

        with patch("extract_msg.Message", return_value=mock_email):
            msg_report = agent.ingest_document(msg_path)
            assert msg_report["status"] == "success"
            assert msg_report["chunks_count"] >= 1
            print(f"  ✔ MSG 邮件入库成功: 分类为 [{msg_report['category']}], 切片数: {msg_report['chunks_count']}")

            # 提问邮件决议内容，验证出处包含发件人与时间
            msg_qa = agent.ask("王总对AIW协议终审的决议内容是什么？")
            assert len(msg_qa["sources"]) > 0
            top_msg_source = msg_qa["sources"][0]
            assert "王总" in top_msg_source["location_label"]
            print(f"  ✔ 邮件问答精准溯源至发件人与通信时间: [{top_msg_source['location_label']}] (得分: {top_msg_source['score']})")

        print("\n" + "=" * 65)
        print("🎉 恭喜！全部 10 项端到端自检测试均 100% 通过！")
        print("=" * 65)

    finally:
        # 无论测试成功或异常中断，强制清理整个沙箱临时目录
        if sandbox_dir.exists():
            shutil.rmtree(sandbox_dir)
            print("🧹 [自动清理] 已将测试沙箱及其生成的所有临时文档彻底销毁，data/ 目录无任何残留！")


if __name__ == "__main__":
    run_all_tests()
