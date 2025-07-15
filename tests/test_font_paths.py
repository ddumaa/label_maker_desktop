import os
import sys
import unittest
import importlib
import tempfile
from pathlib import Path

from reportlab.pdfbase import pdfmetrics


class FontPathResolutionTests(unittest.TestCase):
    """Ensure fonts are registered when module imported from any directory."""

    def test_import_from_other_directory_registers_fonts(self):
        # Путь к корню проекта с модулем label_engine
        repo_root = Path(__file__).resolve().parent.parent
        module_name = "label_engine"

        with tempfile.TemporaryDirectory() as tmpdir:
            prev_cwd = os.getcwd()
            prev_path = sys.path.copy()
            try:
                os.chdir(tmpdir)
                sys.path.insert(0, str(repo_root))
                if module_name in sys.modules:
                    del sys.modules[module_name]
                importlib.invalidate_caches()
                __import__(module_name)
                self.assertIn("DejaVuSans", pdfmetrics.getRegisteredFontNames())
                self.assertIn(
                    "DejaVuSans-Bold", pdfmetrics.getRegisteredFontNames()
                )
            finally:
                os.chdir(prev_cwd)
                sys.path = prev_path


if __name__ == "__main__":
    unittest.main()
