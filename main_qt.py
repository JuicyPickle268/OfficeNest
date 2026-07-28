"""
Mother v2 Qt 面板入口。
python main_qt.py
"""
import sys, os
from pathlib import Path

# 切换到项目根目录
os.chdir(Path(__file__).parent)
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")  # HuggingFace 国内镜像

sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication
from panel.panel_qt import MotherPanelQt


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MotherPanelQt("config/default.yaml")
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
