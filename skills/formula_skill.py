"""
公式 Skill —— LLM 写公式，计算机算。

定位:
    LLM 算术能力差，尤其复杂公式。本 Skill 让 LLM 写 Python 表达式，
    由程序安全求值。公式内容来自 LLM 的知识（会计/数学/统计/计算机），
    本模块只保证: ①安全（AST 白名单，杜绝代码注入）②算得准 ③可复用（存 SQLite）。

使用模式:
    - 临时算:   formula_eval("本金*(1+利率)**年限", {"本金": 10000, "利率": 0.05, "年限": 3})
    - 存公式:   formula_save("复利", "本金*(1+利率)**年限", "复利终值计算")
    - 按名算:   formula_calc("复利", {"本金": 10000, "利率": 0.05, "年限": 3})
    - 查公式:   formula_list()
"""
import ast
import math
from skills.base import BaseSkill

# ── 安全求值：AST 白名单 ──────────────────────────────
# 允许的语法节点——只接受纯数学/逻辑表达式
_ALLOWED_NODES = {
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call,
    ast.Name, ast.Constant, ast.BoolOp, ast.Compare,
    ast.List, ast.Tuple, ast.Load,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
    ast.FloorDiv, ast.BitAnd, ast.BitOr, ast.BitXor,
    ast.LShift, ast.RShift, ast.USub, ast.UAdd, ast.Invert,
    ast.And, ast.Or, ast.Not, ast.Eq, ast.NotEq, ast.Lt,
    ast.LtE, ast.Gt, ast.GtE, ast.IfExp,
}

# 允许调用的函数——只有 math 标准库 + 几个通用内建
_FUNCTIONS = {
    # math 标准库（LLM 写数学公式的通用工具）
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "atan2": math.atan2, "sinh": math.sinh, "cosh": math.cosh,
    "tanh": math.tanh, "log": math.log, "log2": math.log2,
    "log10": math.log10, "exp": math.exp, "sqrt": math.sqrt,
    "pow": math.pow, "floor": math.floor, "ceil": math.ceil,
    "trunc": math.trunc, "fabs": math.fabs, "factorial": math.factorial,
    "hypot": math.hypot, "degrees": math.degrees, "radians": math.radians,
    "gcd": math.gcd, "isclose": math.isclose,
    "pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf,
    # 通用内建
    "abs": abs, "round": round, "min": min, "max": max,
    "sum": sum, "len": len, "int": int, "float": float,
    "bool": bool, "str": str, "bin": bin, "hex": hex, "oct": oct,
}


class FormulaEngine:
    """安全求值器：AST 节点白名单 + 函数白名单 + 变量代入。"""

    def __init__(self):
        self._functions = dict(_FUNCTIONS)

    def check(self, expr: str) -> str:
        """校验表达式，返回错误消息或空字符串（通过）。"""
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as e:
            return f"语法错误: {e.msg}"
        for node in ast.walk(tree):
            if type(node) not in _ALLOWED_NODES:
                return f"不允许的语法: {type(node).__name__}"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id not in self._functions:
                    return f"不允许的函数: {node.func.id}（可用: {', '.join(sorted(self._functions)[:20])}...）"
        return ""

    def evaluate(self, expr: str, variables: dict | None = None) -> str:
        """求值表达式，返回结果文本（失败返回友好错误）。"""
        err = self.check(expr)
        if err:
            return f"❌ {err}"
        try:
            tree = ast.parse(expr, mode="eval")
            result = eval(
                compile(tree, "<formula>", "eval"),
                {"__builtins__": {}},
                {**self._functions, **(variables or {})},
            )
            # 格式化：整数不带小数点，浮点取合理精度
            if isinstance(result, bool):
                return f"✅ 结果: {result}"
            if isinstance(result, int):
                return f"✅ 结果: {result}"
            if isinstance(result, float):
                return f"✅ 结果: {round(result, 8)}"
            return f"✅ 结果: {result}"
        except ZeroDivisionError:
            return "❌ 除零错误：请检查分母"
        except TypeError as e:
            return f"❌ 类型错误: {e}（可能变量类型不对，请确认填的是数字）"
        except NameError as e:
            return f"❌ 未定义变量: {e}（请在 variables 中提供该值）"
        except Exception as e:
            return f"❌ 计算失败: {e}"


class FormulaSkill(BaseSkill):
    """4 个工具：保存/列表/按名算/临时算。"""

    def __init__(self, store):
        self._store = store
        self._engine = FormulaEngine()

    @property
    def name(self) -> str:
        return "formula"

    def get_tools(self) -> list[dict]:
        return [
            {"name": "formula_save", "fn": self.formula_save,
             "schema": self._s("保存一个公式供以后复用——会计/经济/数学/统计/计算机公式写一次，下次报名字直接算。公式用 Python 表达式语法（幂用**，乘用*，支持 math 函数如 sqrt/sin/log）", {
                 "name": {"type": "string", "description": "公式名称，如 '个税'、'复利终值'"},
                 "expression": {"type": "string", "description": "表达式，如 '收入*税率-速算扣除'、'本金*(1+利率)**年限'"},
                 "description": {"type": "string", "description": "公式说明，如 '工资个税计算'"},
             }, ["name", "expression"])},
            {"name": "formula_list", "fn": self.formula_list,
             "schema": self._s("列出所有已保存的公式", {})},
            {"name": "formula_calc", "fn": self.formula_calc,
             "schema": self._s("用已保存的公式计算——先 formula_list 确认公式名和变量，再传入实际数值", {
                 "name": {"type": "string", "description": "公式名称，如 '个税'"},
                 "variables": {"type": "object", "description": "变量值映射，如 {'收入': 15000, '税率': 0.1, '速算扣除': 210}"},
             }, ["name", "variables"])},
            {"name": "formula_eval", "fn": self.formula_eval,
             "schema": self._s("直接计算一个临时表达式（不保存）。用于复杂算术——LLM 不要心算，写表达式交给计算机算。支持 math 函数、幂**、变量代入", {
                 "expression": {"type": "string", "description": "表达式，如 '8000*0.15 + 9500*0.1' 或 'sqrt(a**2 + b**2)'"},
                 "variables": {"type": "object", "description": "可选，表达式中的变量值，如 {'a': 3, 'b': 4}"},
             }, ["expression"])},
        ]

    def formula_save(self, name: str, expression: str, description: str = "") -> str:
        err = self._engine.check(expression)
        if err:
            return f"❌ 公式无法保存: {err}"
        return self._store.save(name.strip(), expression, description)

    def formula_list(self) -> str:
        items = self._store.list_all()
        if not items:
            return "（暂无已保存公式）"
        return "\n".join(f"  📐 {r['name']}: {r['expression']}  {('— '+r['description']) if r['description'] else ''}"
                         for r in items)

    def formula_calc(self, name: str, variables: dict | None = None) -> str:
        f = self._store.get(name.strip())
        if not f:
            return f"❌ 公式不存在: {name}（先 formula_list 看有哪些，或 formula_save 保存）"
        return self._engine.evaluate(f["expression"], variables or {})

    def formula_eval(self, expression: str, variables: dict | None = None) -> str:
        return self._engine.evaluate(expression, variables or {})

    @staticmethod
    def _s(desc, props, req=None):
        return {"type": "function", "function": {
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req or []}}}
