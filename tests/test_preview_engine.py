import os
import unittest
from unittest.mock import patch

# Ensure Qt works in headless mode
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets

import preview_engine
from preview_engine import generate_preview_pdf
from database_service import DatabaseConnectionError
import main


class GeneratePreviewPdfTests(unittest.TestCase):
    """Ensure DB errors are logged and re-raised when creating previews."""

    def test_reraises_database_error(self):
        def failing_generator(*args, **kwargs):
            raise DatabaseConnectionError("boom")

        with self.assertLogs("preview_engine", level="ERROR") as cm:
            with self.assertRaises(DatabaseConnectionError):
                generate_preview_pdf(
                    "out.pdf",
                    "SKU",
                    {},
                    {},
                    generator_func=failing_generator,
                )
        self.assertTrue(any("DB ERROR" in msg for msg in cm.output))


class PreviewErrorHandlingTests(unittest.TestCase):
    """Check that GUI handlers show a message box on DB errors."""

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication([])

    def _create_window(self):
        with patch.object(main, "load_settings", return_value={}), patch.object(
            main, "load_db_config", return_value={}), patch.object(
            main.LabelMakerApp, "update_db_status", return_value=None
        ):
            return main.LabelMakerApp()

    def test_show_label_preview_displays_message_box(self):
        window = self._create_window()
        with patch.object(
            main, "generate_preview_pdf", side_effect=DatabaseConnectionError("fail")
        ), patch.object(QtWidgets.QMessageBox, "critical") as mock_critical:
            window.show_label_preview("A")
            mock_critical.assert_called_once()

    def test_show_page_preview_displays_message_box(self):
        window = self._create_window()
        with patch.object(
            main, "generate_preview_pdf", side_effect=DatabaseConnectionError("fail")
        ), patch.object(QtWidgets.QMessageBox, "critical") as mock_critical:
            window.show_page_preview("A")
            mock_critical.assert_called_once()


if __name__ == "__main__":
    unittest.main()
