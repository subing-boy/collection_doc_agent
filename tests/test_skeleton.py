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
        print("\n[测试 6/6] 执行长句实体提取与口语化意图探测测试...")
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

        print("\n" + "=" * 65)
        print("🎉 恭喜！全部 6 项端到端自检测试均 100% 通过！")
        print("=" * 65)

    finally:
        # 无论测试成功或异常中断，强制清理整个沙箱临时目录
        if sandbox_dir.exists():
            shutil.rmtree(sandbox_dir)
            print("🧹 [自动清理] 已将测试沙箱及其生成的所有临时文档彻底销毁，data/ 目录无任何残留！")


if __name__ == "__main__":
    run_all_tests()
