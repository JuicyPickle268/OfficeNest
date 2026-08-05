"""
公式引擎单元测试 —— 项目第一个测试文件。

运行: python -m unittest tests.test_formula -v
覆盖:
    - 基础算术（加减乘除/幂/取模/整除）
    - 位运算 / 逻辑运算 / 比较
    - math 函数与常量
    - 变量代入（含中文变量名）
    - 列表/元组/条件表达式
    - 安全：注入攻击全部被拒
    - 错误处理：除零/未定义变量/非法语法
"""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.formula_skill import FormulaEngine


class TestBasicArithmetic(unittest.TestCase):
    def setUp(self):
        self.e = FormulaEngine()

    def test_add_sub(self):
        self.assertEqual(self.e.evaluate("8000*0.15 + 9500*0.1"), "✅ 结果: 2150.0")

    def test_power(self):
        self.assertEqual(self.e.evaluate("2**10"), "✅ 结果: 1024")

    def test_compound_interest(self):
        r = self.e.evaluate("本金*(1+利率)**年限", {"本金": 10000, "利率": 0.05, "年限": 3})
        self.assertEqual(r, "✅ 结果: 11576.25")

    def test_mod_floor(self):
        self.assertEqual(self.e.evaluate("17 % 5"), "✅ 结果: 2")
        self.assertEqual(self.e.evaluate("17 // 5"), "✅ 结果: 3")

    def test_float_result(self):
        self.assertEqual(self.e.evaluate("1/3"), "✅ 结果: 0.33333333")


class TestMathFunctions(unittest.TestCase):
    def setUp(self):
        self.e = FormulaEngine()

    def test_sqrt_and_sin(self):
        self.assertEqual(self.e.evaluate("sqrt(144) + sin(pi/2)"), "✅ 结果: 13.0")

    def test_log_exp(self):
        self.assertEqual(self.e.evaluate("log(e)"), "✅ 结果: 1.0")
        self.assertEqual(self.e.evaluate("log10(100)"), "✅ 结果: 2.0")

    def test_constants(self):
        self.assertEqual(self.e.evaluate("round(pi, 4)"), "✅ 结果: 3.1416")
        self.assertEqual(self.e.evaluate("round(tau, 4)"), "✅ 结果: 6.2832")

    def test_factorial(self):
        self.assertEqual(self.e.evaluate("factorial(5)"), "✅ 结果: 120")

    def test_bin_hex(self):
        self.assertEqual(self.e.evaluate("bin(10)"), "✅ 结果: 0b1010")
        self.assertEqual(self.e.evaluate("hex(255)"), "✅ 结果: 0xff")


class TestBitwiseAndLogic(unittest.TestCase):
    def setUp(self):
        self.e = FormulaEngine()

    def test_bitwise(self):
        self.assertEqual(self.e.evaluate("(0b1100 & 0b1010) | 0b1"), "✅ 结果: 9")
        self.assertEqual(self.e.evaluate("1 << 4"), "✅ 结果: 16")
        self.assertEqual(self.e.evaluate("0xFF ^ 0x0F"), "✅ 结果: 240")

    def test_logic_compare(self):
        self.assertEqual(self.e.evaluate("5 > 3 and 2 < 4"), "✅ 结果: True")
        self.assertEqual(self.e.evaluate("not (1 == 2)"), "✅ 结果: True")

    def test_ifexp(self):
        self.assertEqual(self.e.evaluate("10 if 5 > 3 else 0"), "✅ 结果: 10")


class TestListsAndAggregation(unittest.TestCase):
    def setUp(self):
        self.e = FormulaEngine()

    def test_list_ops(self):
        self.assertEqual(self.e.evaluate("sum([1,2,3,4,5])"), "✅ 结果: 15")
        self.assertEqual(self.e.evaluate("max([3,7,2]) - min([3,7,2])"), "✅ 结果: 5")
        self.assertEqual(self.e.evaluate("len([1,2,3])"), "✅ 结果: 3")

    def test_nested_calls(self):
        self.assertEqual(self.e.evaluate("sqrt(sum([9,16]))"), "✅ 结果: 5.0")


class TestSecurity(unittest.TestCase):
    """注入攻击必须全部被拒。"""

    def setUp(self):
        self.e = FormulaEngine()

    def test_import_attack(self):
        r = self.e.evaluate('__import__("os").system("echo hacked")')
        self.assertIn("❌", r)

    def test_attribute_attack(self):
        r = self.e.evaluate("().__class__.__bases__")
        self.assertIn("❌", r)

    def test_subscript_attack(self):
        r = self.e.evaluate('"".__class__.__mro__[1]')
        self.assertIn("❌", r)

    def test_unallowed_function(self):
        r = self.e.evaluate("open('x')")
        self.assertIn("❌", r)

    def test_unallowed_builtin(self):
        r = self.e.evaluate("eval('1+1')")
        self.assertIn("❌", r)


class TestErrors(unittest.TestCase):
    def setUp(self):
        self.e = FormulaEngine()

    def test_zero_division(self):
        self.assertIn("除零", self.e.evaluate("1/0"))

    def test_undefined_variable(self):
        self.assertIn("未定义变量", self.e.evaluate("x + 1"))

    def test_syntax_error(self):
        self.assertIn("语法错误", self.e.evaluate("1 +"))

    def test_wrong_type(self):
        self.assertIn("❌", self.e.evaluate("'a' + 1"))


if __name__ == "__main__":
    unittest.main()
