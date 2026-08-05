"""
PDF 读取工具单元测试。

运行: python -m unittest tests.test_pdf_tools -v
覆盖:
    - pdf_read 页码范围读取（超长 PDF 分段）
    - pdf_read 向后兼容（默认从头读）
    - pdf_analyze_range 批量入队
    - vision_get_result 取结果（完成/待处理/不存在）
"""
import unittest
import sys
import asyncio
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.vision_skill import VisionSkill


def make_test_pdf(pages: int = 5) -> Path:
    """生成 N 页含文本的测试 PDF。"""
    import fitz
    p = Path(tempfile.mkdtemp()) / f"test_{pages}p.pdf"
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"第{i+1}页内容 PAGE{i+1}")
    doc.save(str(p))
    doc.close()
    return p


class FakeQueue:
    def __init__(self):
        self.items = {}
        self.n = 0

    def add(self, img, prompt):
        self.n += 1
        tid = f"vq_test{self.n}"
        self.items[tid] = {"status": "done", "result": f"分析结果{self.n}", "error": ""}
        return tid

    def get_result(self, tid):
        return self.items.get(tid)

    def status(self):
        return {"done": self.n, "pending": 0, "failed": 0}


class TestPdfReadPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pdf = make_test_pdf(5)
        cls.vs = VisionSkill(glm_api_key="", sense_api_key="")

    def test_range_read(self):
        r = self.vs.pdf_read(str(self.pdf), max_pages=2, start_page=3)
        self.assertIn("第3-4页", r)
        self.assertIn("PAGE3", r)
        self.assertIn("PAGE4", r)
        self.assertNotIn("PAGE1", r)

    def test_backward_compat(self):
        r = self.vs.pdf_read(str(self.pdf), max_pages=2)
        self.assertIn("第1-2页", r)
        self.assertIn("PAGE1", r)

    def test_page_boundary(self):
        r = self.vs.pdf_read(str(self.pdf), max_pages=10, start_page=4)
        self.assertIn("第4-5页", r)  # 超过总页数应截断到最后一页

    def test_nonexistent_file(self):
        r = self.vs.pdf_read("/nonexistent/x.pdf")
        self.assertIn("❌", r)


class TestPdfAnalyzeRange(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pdf = make_test_pdf(5)

    def test_batch_enqueue(self):
        vs = VisionSkill(glm_api_key="", sense_api_key="", queue=FakeQueue())
        r = asyncio.run(vs.pdf_analyze_range(str(self.pdf), 1, 3, "提取内容"))
        self.assertIn("已入队 3 页", r)
        self.assertIn("vq_test1", r)

    def test_get_result_done(self):
        vs = VisionSkill(glm_api_key="", sense_api_key="", queue=FakeQueue())
        asyncio.run(vs.pdf_analyze_range(str(self.pdf), 1, 1, "提取内容"))
        r = vs.vision_get_result("vq_test1")
        self.assertIn("分析结果1", r)

    def test_get_result_missing(self):
        vs = VisionSkill(glm_api_key="", sense_api_key="", queue=FakeQueue())
        r = vs.vision_get_result("vq_nope")
        self.assertIn("不存在", r)

    def test_get_result_pending(self):
        q = FakeQueue()
        q.items = {"vq_pending": {"status": "pending", "result": "", "error": ""}}
        vs = VisionSkill(glm_api_key="", sense_api_key="", queue=q)
        r = vs.vision_get_result("vq_pending")
        self.assertIn("处理中", r)

    def test_no_queue(self):
        vs = VisionSkill(glm_api_key="", sense_api_key="")  # 无 queue
        r = vs.vision_get_result("vq_x")
        self.assertIn("未启用", r)


class TestToolRegistry(unittest.TestCase):
    def test_new_tools_registered(self):
        vs = VisionSkill(glm_api_key="", sense_api_key="")
        names = [t["name"] for t in vs.get_tools()]
        self.assertIn("pdf_analyze_range", names)
        self.assertIn("vision_get_result", names)
        self.assertIn("pdf_read", names)


if __name__ == "__main__":
    unittest.main()
