"""
==============================================================================
模块名称: parsers/excel_parser.py
功能描述: Excel 工作簿 (.xlsx) 结构化表格解析器
          基于 openpyxl 实现多工作表 (Sheet) 遍历与表头自解释切片：
          1. 自动提取各工作表表头行，保持二维表格的列语义绑定；
          2. 以 25 行为原子区间生成携带表头的 Markdown 表格切片；
          3. 出处坐标精确记录至工作表名称与行号区间（如: '工作表: 成本明细, 第2-26行'）。
可移植性: 纯 Python 依赖 openpyxl，只读数据计算值 (data_only=True)。
==============================================================================
"""

from pathlib import Path
from typing import List, Optional
import openpyxl

from parsers.base_parser import BaseParser, DocumentChunk, ParsedDocument


class ExcelParser(BaseParser):
    """
    Excel (.xlsx) 工作簿表格解析器
    """

    def supports(self, file_path: Path) -> bool:
        """检查文件后缀是否为 .xlsx 或 .xlsm"""
        return file_path.suffix.lower() in [".xlsx", ".xlsm"]

    def parse(self, file_path: Path, doc_id: Optional[str] = None) -> ParsedDocument:
        """
        解析 Excel 工作簿，按 Sheet 和行区间切片
        """
        file_path = Path(file_path).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"未找到指定的 Excel 文件: {file_path}")

        document_id = doc_id or self.generate_id()
        chunks: List[DocumentChunk] = []
        preview_texts: List[str] = []

        # 以只读且读取计算值模式打开工作簿
        wb = openpyxl.load_workbook(str(file_path), data_only=True, read_only=True)

        try:
            global_chunk_idx = 1
            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                rows_iter = sheet.iter_rows(values_only=True)

                # 读取第一行作为表头
                try:
                    first_row = next(rows_iter, None)
                except Exception:
                    first_row = None

                if not first_row:
                    continue

                # 格式化表头列表
                headers = [
                    str(cell).strip() if cell is not None else f"列{idx}"
                    for idx, cell in enumerate(first_row, start=1)
                ]

                # 收集用于大模型分类的前情提要预览
                preview_texts.append(f"【工作表: {sheet_name}】 表头: {', '.join(headers[:8])}")

                # 收集后续数据行
                data_rows: List[List[str]] = []
                current_start_row = 2

                for row_idx, row_values in enumerate(rows_iter, start=2):
                    # 判断是否全空行
                    if not any(v is not None and str(v).strip() for v in row_values):
                        continue

                    # 格式化单元格值
                    row_cells = [
                        str(v).strip().replace("\n", " ") if v is not None else "-"
                        for v in row_values[:len(headers)]
                    ]
                    # 补齐长度
                    if len(row_cells) < len(headers):
                        row_cells.extend(["-"] * (len(headers) - len(row_cells)))

                    data_rows.append(row_cells)

                    # 用于全局预览的前几行数据
                    if len("".join(preview_texts)) < 1200 and len(data_rows) <= 3:
                        preview_texts.append(f"  行{row_idx}: {', '.join(row_cells[:6])}")

                    # 达到 25 行为一组时切出一个自解释 Chunk
                    if len(data_rows) >= 25:
                        chunk = self._create_sheet_chunk(
                            document_id=document_id,
                            filename=file_path.name,
                            sheet_name=sheet_name,
                            headers=headers,
                            data_rows=data_rows,
                            start_row=current_start_row,
                            end_row=row_idx,
                            chunk_seq=global_chunk_idx
                        )
                        chunks.append(chunk)
                        global_chunk_idx += 1
                        data_rows = []
                        current_start_row = row_idx + 1

                # 刷新最后剩余的行数据
                if data_rows:
                    end_row = current_start_row + len(data_rows) - 1
                    chunk = self._create_sheet_chunk(
                        document_id=document_id,
                        filename=file_path.name,
                        sheet_name=sheet_name,
                        headers=headers,
                        data_rows=data_rows,
                        start_row=current_start_row,
                        end_row=end_row,
                        chunk_seq=global_chunk_idx
                    )
                    chunks.append(chunk)
                    global_chunk_idx += 1

        finally:
            wb.close()

        full_preview = "\n".join(preview_texts)

        return ParsedDocument(
            doc_id=document_id,
            filename=file_path.name,
            file_type="xlsx",
            total_pages=len(chunks),
            full_text_preview=full_preview,
            chunks=chunks
        )

    def _create_sheet_chunk(
        self,
        document_id: str,
        filename: str,
        sheet_name: str,
        headers: List[str],
        data_rows: List[List[str]],
        start_row: int,
        end_row: int,
        chunk_seq: int
    ) -> DocumentChunk:
        """
        生成带有表头自解释能力的 Markdown 表格切片
        """
        table_lines = [
            f"【工作表名称】: {sheet_name} (数据行区间: 第{start_row}行 ~ 第{end_row}行)",
            "",
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |"
        ]

        for r in data_rows:
            table_lines.append("| " + " | ".join(r) + " |")

        # 针对较窄表格（<= 6列），额外追加键值对自然语句，极大增强稠密向量语义匹配度
        if len(headers) <= 6:
            table_lines.append("\n【逐行键值详情】:")
            for idx, r in enumerate(data_rows, start=start_row):
                kv_pairs = [f"{h}={val}" for h, val in zip(headers, r) if val != "-"]
                table_lines.append(f"• [第{idx}行]: {', '.join(kv_pairs)}")

        content_str = "\n".join(table_lines)
        location_label = f"工作表: {sheet_name}, 第{start_row}-{end_row}行"

        return DocumentChunk(
            chunk_id=self.generate_id(),
            doc_id=document_id,
            source_filename=filename,
            chunk_type="sheet_table",
            page_or_slide=chunk_seq,
            location_label=location_label,
            content=content_str
        )
