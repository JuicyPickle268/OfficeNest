"""
MD → PDF：markdown → HTML → Edge 打印 PDF → 输出。
用法: python md_to_pdf.py <输入.md> <输出.pdf>
"""
import sys, subprocess, tempfile, traceback
from pathlib import Path

def main():
    try:
        md_path = Path(sys.argv[1]).resolve()
        out_path = Path(sys.argv[2]).resolve()

        import markdown
        md = md_path.read_text(encoding="utf-8")
        html_body = markdown.markdown(md, extensions=["tables", "fenced_code"])
        css = """
        body { font-family: 'Microsoft YaHei', sans-serif; max-width: 860px;
               margin: 0 auto; padding: 40px 48px; color: #24292f;
               line-height: 1.75; font-size: 15px; }
        h1 { font-size: 26px; border-bottom: 2px solid #0969da; padding-bottom: 10px; color: #0969da; }
        h2 { font-size: 21px; margin-top: 32px; border-bottom: 1px solid #d0d7de; padding-bottom: 6px; }
        h3 { font-size: 17px; margin-top: 24px; }
        blockquote { border-left: 4px solid #0969da; background: #f6f8fa; margin: 12px 0;
                     padding: 10px 16px; border-radius: 4px; color: #57606a; }
        code { background: #f6f8fa; border-radius: 4px; padding: 2px 6px;
               font-family: Consolas, monospace; font-size: 13px; color: #cf222e; }
        pre { background: #f6f8fa; border-radius: 6px; padding: 14px 16px; overflow-x: auto; }
        table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 14px; }
        th, td { border: 1px solid #d0d7de; padding: 8px 12px; text-align: left; }
        th { background: #f6f8fa; }
        """
        html = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{css}</style></head><body>{html_body}</body></html>"

        tmp = Path(tempfile.gettempdir()) / "md2pdf"
        tmp.mkdir(exist_ok=True)
        tmp_html = tmp / "doc.html"
        tmp_pdf = tmp / "doc.pdf"
        tmp_html.write_text(html, encoding="utf-8")

        edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        url = tmp_html.as_uri()
        print(f"[1/2] Edge 渲染: {url}")
        r = subprocess.run(
            [edge, "--headless", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={tmp_pdf}", url],
            capture_output=True, timeout=120,
        )
        if not tmp_pdf.exists():
            print("❌ PDF 未生成, edge stderr:", r.stderr.decode("utf-8", "ignore")[:500])
            return 1
        import shutil
        shutil.copy(tmp_pdf, out_path)
        print(f"[2/2] ✅ 已输出: {out_path} ({out_path.stat().st_size/1024:.0f}KB)")
        return 0
    except Exception:
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
