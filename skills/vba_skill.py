"""
Excel VBA Skill —— LLM 可调用的 VBA 宏操作工具。
通过 win32com 注入/执行 VBA 代码，处理 openpyxl 做不到的复杂操作。
"""
from pathlib import Path
from skills.base import BaseSkill


class VBASkill(BaseSkill):

    def __init__(self):
        pass

    @property
    def name(self) -> str:
        return "vba"

    def get_tools(self) -> list[dict]:
        return [
            {"name": "excel_vba_add", "fn": self.excel_vba_add,
             "schema": self._s("向 Excel 文件添加 VBA 宏模块并保存为 .xlsm（需用 win32com 操作）", {
                 "filepath": {"type": "string", "description": "Excel 文件路径（自动转为 .xlsm）"},
                 "code": {"type": "string", "description": "VBA 代码，不含 Sub/End Sub 外的声明"},
                 "macro_name": {"type": "string", "description": "宏名称，如 ProcessData"},
             }, ["filepath", "code", "macro_name"])},
            {"name": "excel_vba_run", "fn": self.excel_vba_run,
             "schema": self._s("执行 Excel 文件中已有的 VBA 宏", {
                 "filepath": {"type": "string", "description": "Excel 文件路径"},
                 "macro_name": {"type": "string", "description": "要运行的宏名称"},
             }, ["filepath", "macro_name"])},
        ]

    def excel_vba_add(self, filepath: str, code: str, macro_name: str) -> str:
        path = Path(filepath.strip('"').strip("'").strip() if filepath else "")
        if not path.is_absolute():
            path = Path("./workbooks") / path.name
        if path.suffix not in ('.xlsm',):
            path = path.with_suffix('.xlsm')

        try:
            import win32com.client
            excel = win32com.client.Dispatch("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False

            # 打开或创建
            if path.exists():
                wb = excel.Workbooks.Open(str(path.resolve()))
            else:
                wb = excel.Workbooks.Add()
                path.parent.mkdir(parents=True, exist_ok=True)

            # 检查是否已有同名模块
            vb_comp = None
            try:
                vb_comp = wb.VBProject.VBComponents(macro_name)
            except Exception:
                pass

            if vb_comp:
                wb.VBProject.VBComponents.Remove(vb_comp)

            # 添加新模块
            full_code = f"Public Sub {macro_name}()\n{code}\nEnd Sub"
            module = wb.VBProject.VBComponents.Add(1)  # 1 = vbext_ct_StdModule
            module.Name = macro_name
            module.CodeModule.AddFromString(full_code)

            wb.SaveAs(str(path.resolve()), FileFormat=52)  # 52 = xlOpenXMLWorkbookMacroEnabled
            wb.Close()
            excel.Quit()
            return f"✅ VBA 宏「{macro_name}」已注入 {path.name}"
        except Exception as e:
            # 常见错误：VBA 信任设置
            if "VBProject" in str(e):
                return ("❌ 无法访问 VBA 工程。请在 Excel → 文件 → 选项 → 信任中心 → "
                        "信任中心设置 → 宏设置 → 勾选「信任对 VBA 工程对象模型的访问」")
            return f"❌ VBA 注入失败: {e}"

    def excel_vba_run(self, filepath: str, macro_name: str) -> str:
        path = Path(filepath.strip('"').strip("'").strip() if filepath else "")
        if not path.is_absolute():
            path = Path("./workbooks") / path.name
        if not path.exists():
            return f"❌ 文件不存在: {path.name}"

        try:
            import win32com.client
            excel = win32com.client.Dispatch("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False

            wb = excel.Workbooks.Open(str(path.resolve()))
            full_name = f"{path.stem}!{macro_name}"
            result = excel.Application.Run(full_name)
            wb.Save()
            wb.Close()
            excel.Quit()
            return f"✅ VBA 宏「{macro_name}」执行完成" + (f"，返回: {result}" if result else "")
        except Exception as e:
            return f"❌ VBA 执行失败: {e}"
