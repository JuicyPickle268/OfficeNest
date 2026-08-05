"""
MD → 长图工具：markdown → HTML → Edge 打印 PDF → PyMuPDF 拼接长图 PNG。
用法: python md_to_longimage.py <输入.md> [输出.png] [宽度px]
"""
import sys, subprocess, tempfile
from pathlib import Path

WIDTH = 900  # 长图宽度（px），对应页面宽度

def main():
    md_path = Path(sys.argv[1]).resolve()
    out_path = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else md_path.with_suffix(".png")
    width = int(sys.argv[3]) if len(sys.argv) > 3 else WIDTH

    import markdown
    html_body = markdown.markdown(md_path.read_text(encoding="utf-8"), extensions=["tables", "fenced_code"])

    # 好看的样式（浅色，适合分享）
    css = """
    body { font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; max-width: 860px;
           margin: 0 auto; padding: 40px 48px; color: #24292f; line-height: 1.75;
           font-size: 15px; background: #ffffff; }
    h1 { font-size: 26px; border-bottom: 2px solid #0969da; padding-bottom: 10px; color: #0969da; }
    h2 { font-size: 21px; margin-top: 32px; border-bottom: 1px solid #d0d7de; padding-bottom: 6px; color: #1f2328; }
    h3 { font-size: 17px; margin-top: 24px; color: #1f2328; }
    blockquote { border-left: 4px solid #0969da; background: #f6f8fa; margin: 12px 0;
                 padding: 10px 16px; border-radius: 4px; color: #57606a; }
    blockquote p { margin: 4px 0; }
    code { background: #f6f8fa; border-radius: 4px; padding: 2px 6px; font-family: Consolas, monospace;
           font-size: 13px; color: #cf222e; }
    pre { background: #f6f8fa; border-radius: 6px; padding: 14px 16px; overflow-x: auto; }
    pre code { background: none; padding: 0; color: #24292f; }
    table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 14px; }
    th, td { border: 1px solid #d0d7de; padding: 8px 12px; text-align: left; }
    th { background: #f6f8fa; font-weight: 600; }
    hr { border: none; border-top: 1px solid #d0d7de; margin: 24px 0; }
    li { margin: 4px 0; }
    """
    html = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{css}</style></head><body>{html_body}</body></html>"

    tmp_html = Path(tempfile.gettempdir()) / "thinking_log_render.html"
    tmp_pdf = Path(tempfile.gettempdir()) / "thinking_log_render.pdf"
    tmp_html.write_text(html, encoding="utf-8")

    # Edge headless 打印 PDF（无头模式）
    edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    r = subprocess.run([
        edge, "--headless", "--disable-gpu", "--no-pdf-header-footer",
        f"--print-to-pdf={tmp_pdf}", f"file:///{tmp_html}",
    ], capture_output=True, timeout=120)
    if not tmp_pdf.exists():
        print("❌ PDF 生成失败:", r.stderr.decode("utf-8", "ignore")[:300])
        sys.exit(1)

    # PyMuPDF 拼接所有页为一张长图
    import fitz
    doc = fitz.open(str(tmp_pdf))
    pixmaps = []
    total_h = 0
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(width / page.rect.width, width / page.rect.width))
        pixmaps.append(pix)
        total_h += pix.height
    max_w = max(p.width for p in pixmaps)

    canvas = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, max_w, total_h))
    canvas.clear_with(255)  # 白底
    y = 0
    for pix in pixmaps:
        canvas.copy(pix, fitz.IRect(0, y, pix.width, y + pix.height))
        y += pix.height
    canvas.save(str(out_path))
    doc.close()

    print(f"✅ 长图已生成: {out_path}（{len(pixmaps)} 页，{max_w}x{total_h}px，{out_path.stat().st_size/1024:.0f}KB）")

if __name__ == "__main__":
    main()
