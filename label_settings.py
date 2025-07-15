from PyQt5 import QtWidgets
import os

class LabelSettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, current_settings=None):
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

        self.output_file = QtWidgets.QLineEdit(current_settings.get("output_file", "labels.pdf"))

        self.care_image_input = QtWidgets.QLineEdit(current_settings.get("care_image_url", ""))
        self.browse_button = QtWidgets.QPushButton("📁")
        self.browse_button.clicked.connect(self.select_image)

        care_layout = QtWidgets.QHBoxLayout()
        care_layout.addWidget(self.care_image_input)
        care_layout.addWidget(self.browse_button)

        layout.addRow("Ширина страницы (мм):", self.page_width)
        layout.addRow("Высота страницы (мм):", self.page_height)
        layout.addRow("Ширина этикетки (мм):", self.label_width)
        layout.addRow("Размер шрифта:", self.font_size)
        layout.addRow("Имя PDF-файла:", self.output_file)
        layout.addRow("Изображение ухода (URL или путь):", care_layout)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.setLayout(layout)

    def select_image(self):
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Выбрать изображение", "", "Images (*.png *.jpg *.jpeg)")
        if filepath:
            self.care_image_input.setText(filepath)

    def get_settings(self):
        return {
            "page_width_mm": self.page_width.value(),
            "page_height_mm": self.page_height.value(),
            "label_width_mm": self.label_width.value(),
            "font_size": self.font_size.value(),
            "output_file": self.output_file.text(),
            "care_image_url": self.care_image_input.text()
        }