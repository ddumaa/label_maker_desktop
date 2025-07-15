from PyQt5 import QtWidgets
import os

class LabelSettingsDialog(QtWidgets.QDialog):
    """Dialog window for editing PDF label parameters."""

    def __init__(self, parent=None, current_settings=None):
        """Create dialog with current label settings."""
        super().__init__(parent)
        self.setWindowTitle("Настройки этикетки")
        self.setModal(True)

        layout = QtWidgets.QFormLayout()

        self.page_width = QtWidgets.QSpinBox()
        self.page_width.setMaximum(1000)
        self.page_width.setValue(current_settings.get("page_width_mm", 120))

        self.page_height = QtWidgets.QSpinBox()
        self.page_height.setMaximum(1000)
        self.page_height.setValue(current_settings.get("page_height_mm", 70))

        self.label_width = QtWidgets.QSpinBox()
        self.label_width.setMaximum(1000)
        self.label_width.setValue(current_settings.get("label_width_mm", 40))

        self.font_size = QtWidgets.QSpinBox()
        self.font_size.setMaximum(100)
        self.font_size.setValue(current_settings.get("font_size", 6))

        self.min_line_height = QtWidgets.QDoubleSpinBox()
        self.min_line_height.setDecimals(1)
        self.min_line_height.setMaximum(100)
        self.min_line_height.setValue(current_settings.get("min_line_height_mm", 2.0))

        self.barcode_height = QtWidgets.QSpinBox()
        self.barcode_height.setMaximum(100)
        self.barcode_height.setValue(current_settings.get("barcode_height_mm", 6))

        self.bottom_margin = QtWidgets.QSpinBox()
        self.bottom_margin.setMaximum(100)
        self.bottom_margin.setValue(current_settings.get("bottom_margin_mm", 0))

        self.top_margin = QtWidgets.QSpinBox()
        self.top_margin.setMaximum(100)
        self.top_margin.setValue(current_settings.get("top_margin_mm", 2))

        self.output_file = QtWidgets.QLineEdit(current_settings.get("output_file", "labels.pdf"))

        self.labels_per_page = QtWidgets.QSpinBox()
        self.labels_per_page.setMaximum(100)
        self.labels_per_page.setValue(current_settings.get("labels_per_page", 3))

        self.use_stock_checkbox = QtWidgets.QCheckBox("Учитывать количество на складе")
        self.use_stock_checkbox.setChecked(current_settings.get("use_stock_quantity", True))

        self.care_image_input = QtWidgets.QLineEdit(current_settings.get("care_image_path", ""))
        self.browse_button = QtWidgets.QPushButton("📁")
        self.browse_button.clicked.connect(self.select_image)

        care_layout = QtWidgets.QHBoxLayout()
        care_layout.addWidget(self.care_image_input)
        care_layout.addWidget(self.browse_button)

        layout.addRow("Ширина страницы (мм):", self.page_width)
        layout.addRow("Высота страницы (мм):", self.page_height)
        layout.addRow("Ширина этикетки (мм):", self.label_width)
        layout.addRow("Размер шрифта:", self.font_size)
        layout.addRow("Мин. высота строки (мм):", self.min_line_height)
        layout.addRow("Высота штрихкода (мм):", self.barcode_height)
        layout.addRow("Отступ сверху (мм):", self.top_margin)
        layout.addRow("Отступ снизу (мм):", self.bottom_margin)
        layout.addRow("Имя PDF-файла:", self.output_file)
        layout.addRow("Этикеток на странице:", self.labels_per_page)
        layout.addRow(self.use_stock_checkbox)
        layout.addRow("Изображение ухода (путь или URL):", care_layout)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.setLayout(layout)

    def select_image(self):
        """Open a file dialog to choose care instructions image."""
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Выбрать изображение",
            "",
            "Images (*.png *.jpg *.jpeg)"
        )
        if filepath:
            self.care_image_input.setText(filepath)

    def get_settings(self):
        """Return a settings dictionary based on user input."""
        return {
            "page_width_mm": self.page_width.value(),
            "page_height_mm": self.page_height.value(),
            "label_width_mm": self.label_width.value(),
            "font_size": self.font_size.value(),
            "min_line_height_mm": self.min_line_height.value(),
            "barcode_height_mm": self.barcode_height.value(),
            "bottom_margin_mm": self.bottom_margin.value(),
            "top_margin_mm": self.top_margin.value(),
            "output_file": self.output_file.text(),
            "care_image_path": self.care_image_input.text(),
            "labels_per_page": self.labels_per_page.value(),
            "use_stock_quantity": self.use_stock_checkbox.isChecked()
        }
