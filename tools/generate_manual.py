# -*- coding: utf-8 -*-
"""
tools/generate_manual.py

シフト自動作成システム ユーザーマニュアル PDF 生成スクリプト。
PyQt6 の QTextDocument + QPrinter を使い、追加パッケージ不要で PDF を出力する。

使い方:
    python tools/generate_manual.py [output.pdf]
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUT_DEFAULT = HERE.parent / "シフト自動作成システム_操作マニュアル.pdf"
HTML_FILE = HERE / "manual.html"


def generate_pdf(output_path: Path) -> None:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QTextDocument, QPageSize
    from PyQt6.QtPrintSupport import QPrinter
    from PyQt6.QtCore import QSizeF, QMarginsF
    from PyQt6.QtGui import QPageLayout

    app = QApplication.instance() or QApplication(sys.argv)

    html = HTML_FILE.read_text(encoding="utf-8")

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(output_path))
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageMargins(QMarginsF(20, 20, 20, 20), QPageLayout.Unit.Millimeter)

    doc = QTextDocument()
    doc.setHtml(html)
    doc.setPageSize(QSizeF(printer.pageRect(QPrinter.Unit.Point).size()))

    doc.print(printer)
    print(f"PDF を出力しました: {output_path}")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else OUTPUT_DEFAULT
    generate_pdf(out)
