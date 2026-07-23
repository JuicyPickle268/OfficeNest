"""快速测试表格渲染"""
import sys
sys.path.insert(0, ".")

from adapters.table_renderer import detect_and_render

# 测试 1: Markdown 表格
md = """好的，以下是数据：

| # | 姓名 | 岗位 | 面试官 | 评分 |
|---|------|------|--------|------|
| 1 | 张三 | 产品经理 | 李四 | 95 |
| 2 | 王五 | 前端开发 | — | 87 |
| 3 | 赵六 | 后端开发 | 刘八 | 不及格 |

共 3 条记录。"""

print("=== 原始 ===")
print(md)
print()
print("=== 渲染 ===")
print(detect_and_render(md))

# 测试 2: 纯管道分隔（无 Markdown 分隔行）
print()
print("=== 纯管道 ===")
print(detect_and_render("| 姓名 | 分数 |\n| 张三 | 95 |\n| 李四 | 87 |"))
