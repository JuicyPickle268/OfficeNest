"""
终端表格渲染器。
自动检测 Markdown 表格、制表符数据、管道分隔数据，渲染为对齐的 ASCII 表格。
"""
import re


def detect_and_render(text: str, max_col_width: int = 20) -> str:
    """
    检测文本中的表格并格式化。
    支持：Markdown 表格、TSV、管道分隔。

    返回：格式化后的文本（表格部分被替换为 ASCII 表格）。
    """
    lines = text.split("\n")
    result = []
    table_block = []
    in_table = False

    for line in lines:
        is_table_line = _is_md_table_line(line) or _is_pipe_data(line)

        if is_table_line:
            table_block.append(line)
            in_table = True
        else:
            if in_table and table_block:
                result.append(_render_table(table_block, max_col_width))
                result.append("")  # 表格后空一行
                table_block = []
                in_table = False
            result.append(line)

    # 末尾的表格
    if table_block:
        result.append(_render_table(table_block, max_col_width))

    return "\n".join(result)


def _is_md_table_line(line: str) -> bool:
    """检测 Markdown 表格分隔行：| --- | --- |"""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return False
    # 分隔行特征：只有 |、-、:、空格
    inner = stripped[1:-1]
    return bool(re.match(r'^[\s\-:|]+$', inner))


def _is_pipe_data(line: str) -> bool:
    """检测管道分隔的数据行：| A | B | C |"""
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def _render_table(block: list[str], max_col_width: int = 20) -> str:
    """将表格块渲染为对齐的 ASCII 表格。"""
    # 解析所有行
    rows = []
    separator_idx = -1

    for i, line in enumerate(block):
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if _is_md_table_line(line):
            separator_idx = i
            # 解析对齐方式
            alignments = []
            for c in cells:
                c = c.strip()
                if c.startswith(":") and c.endswith(":"):
                    alignments.append("^")
                elif c.endswith(":"):
                    alignments.append(">")
                else:
                    alignments.append("<")
            rows.append(("sep", cells, alignments))
        else:
            rows.append(("data", cells, []))

    if len(rows) < 2:
        return "\n".join(block)

    # 过滤出数据行
    data_rows = [r for r in rows if r[0] == "data"]
    sep_rows = [r for r in rows if r[0] == "sep"]

    if not data_rows:
        return "\n".join(block)

    # 计算每列最大宽度
    all_data_cells = [r[1] for r in data_rows]
    col_count = max(len(cells) for cells in all_data_cells)
    col_widths = [0] * col_count

    for cells in all_data_cells:
        for j, cell in enumerate(cells):
            col_widths[j] = max(col_widths[j], min(len(cell), max_col_width))

    # 确保最小宽度
    col_widths = [max(w, 3) for w in col_widths]

    # 截断过长内容
    def trunc(cell, width):
        s = str(cell)
        if len(s) > width:
            return s[:width - 1] + "…"
        return s

    # 获取对齐（从分隔行），默认左对齐
    alignments = ["<"] * col_count
    if sep_rows:
        sep_cells = sep_rows[0][1]
        sep_aligns = sep_rows[0][2]
        for j in range(min(col_count, len(sep_aligns))):
            alignments[j] = sep_aligns[j]

    # 构建边框
    sep_line = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

    result_lines = [sep_line]

    for i, (_, cells, _) in enumerate(data_rows):
        # 补齐缺失列
        while len(cells) < col_count:
            cells.append("")
        # 截断
        cells = [trunc(c, col_widths[j]) for j, c in enumerate(cells)]

        # 格式化行
        formatted = "|"
        for j, cell in enumerate(cells):
            align = alignments[j] if j < len(alignments) else "<"
            w = col_widths[j]
            if align == ">":
                formatted += f" {cell:>{w}} "
            elif align == "^":
                formatted += f" {cell:^{w}} "
            else:
                formatted += f" {cell:<{w}} "
            formatted += "|"

        result_lines.append(formatted)
        # 第一行数据后加分隔线
        if i == 0:
            result_lines.append(sep_line)

    result_lines.append(sep_line)
    return "\n".join(result_lines)
