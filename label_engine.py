from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.graphics.barcode import code128
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import simpleSplit
from reportlab.lib.utils import ImageReader
from PIL import Image
import os
import re
import io
import requests
import json
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.graphics import renderPDF
from database_service import DatabaseService, DatabaseConnectionError
from pathlib import Path
import logging

# Логгер модуля используется для вывода предупреждений и ошибок.
logger = logging.getLogger(__name__)

# === НАСТРОЙКИ ===

# Connection configuration will be supplied at runtime.

def load_skus_from_file(filepath):
    """Return SKU list from text file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

# Значения по умолчанию для настроек PDF-генератора
DEFAULT_OUTPUT_FILE = "labels.pdf"
DEFAULT_CARE_IMAGE_PATH = "care.png"
DEFAULT_PAGE_WIDTH_MM = 120
DEFAULT_PAGE_HEIGHT_MM = 70
DEFAULT_LABEL_WIDTH_MM = 40
DEFAULT_FONT_SIZE = 6
DEFAULT_MIN_LINE_HEIGHT_MM = 2.0
DEFAULT_BARCODE_HEIGHT_MM = 6
DEFAULT_BOTTOM_MARGIN_MM = 0
DEFAULT_TOP_MARGIN_MM = 2
DEFAULT_LABELS_PER_PAGE = 3

# === РЕГИСТРАЦИЯ ШРИФТОВ ===
# Полные пути к файлам шрифтов. Используем абсолютные пути, чтобы модуль
# работал корректно вне зависимости от текущей рабочей директории.
BASE_DIR = Path(__file__).resolve().parent
FONT_DIR = BASE_DIR / "fonts"

REGULAR_FONT_PATH = FONT_DIR / "DejaVuSans.ttf"
BOLD_FONT_PATH = FONT_DIR / "DejaVuSans-Bold.ttf"

pdfmetrics.registerFont(TTFont("DejaVuSans", str(REGULAR_FONT_PATH)))
pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(BOLD_FONT_PATH)))

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def extract_composition(text: str) -> str | None:
    """Возвращает состав товара из текста описания.

    Parameters
    ----------
    text : str
        Исходный текст описания.

    Returns
    -------
    str | None
        Найденное значение после ``"Состав:"`` или ``None``.
    """
    match = re.search(r"Состав:([^\n\r]*)", text, re.IGNORECASE)
    return match.group(1).strip() if match else None

def extract_manufacturer(text: str) -> str | None:
    """Извлекает строку производителя из описания.

    Parameters
    ----------
    text : str
        Текст, содержащий информацию об изготовителе.

    Returns
    -------
    str | None
        Адрес производителя либо ``None``.
    """
    match = re.search(r"(?:Адрес изготовления|Адрес производителя|Адрес производитель):([^\n\r]*)", text, re.IGNORECASE)
    return match.group(1).strip() if match else None

def extract_measurements(text: str, target_size: str | None) -> str | None:
    """Получить строку замеров для указанного размера.

    Parameters
    ----------
    text : str
        Описание товара с блоком ``"Замеры:"``.
    target_size : str | None
        Размер, по которому ищем замеры.

    Returns
    -------
    str | None
        Отформатированная строка замеров или ``None``.
    """
    log_lines = []
    if not target_size:
        log_lines.append("[SKIP] Нет значения размера\n")
        write_measurement_log(log_lines)
        return None

    block = re.search(r"Замеры:(.*?)(?:\n\n|$)", text, re.DOTALL | re.IGNORECASE)
    if not block:
        log_lines.append(f"[SKIP] Нет блока 'Замеры:' для размера {target_size}\n")
        write_measurement_log(log_lines)
        return None

    lines = block.group(1).splitlines()
    for line in lines:
        log_lines.append(f"Проверка строки: {line}\n")
        match_line = re.match(rf"\s*{target_size}\s*\((.*?)\)", line)
        if match_line:
            inner_text = match_line.group(1).strip()
            if "," in inner_text:
                inner_text = inner_text.split(",", 1)[1].strip()
            parts = []
            keyword_map = {
                "длина от плеча": "длина",
                "длина кофты от плеча": "длина",
                "вся длина от плеча": "длина",
                "вся длина": "длина",
                "рукав до горловины": "рукав",
                "рукав до плеча": "рукав",
                "рукав до капюшона": "рукав",
                "обхват груди": "обхват груди",
                "шаговой": "шаговой",
                "шаговой штанишек": "шаговой",
                "обхват талии": "обхват талии"
            }
            for raw_key, label in keyword_map.items():
                pattern = rf"{re.escape(raw_key)}\s*(\d+\s*см)"
                kmatch = re.search(pattern, inner_text, re.IGNORECASE)
                if kmatch:
                    parts.append(f"{label} {kmatch.group(1).strip()}")
            result = ", ".join(parts) if parts else None
            log_lines.append(f"→ Найдено: {result}\n")
            write_measurement_log(log_lines)
            return result

    log_lines.append("[SKIP] Не найдено совпадений по размеру\n")
    write_measurement_log(log_lines)
    return None

def write_measurement_log(log_lines: list[str]) -> None:
    """Записывает отладочную информацию по замерам в файл."""
    with open("measurements.log", "a", encoding="utf-8") as log:
        log.writelines(log_lines)

def extract_age_as_size(text: str) -> str | None:
    """Пытается определить размер по упоминанию возраста."""
    match = re.search(r"Возраст:?\s*([\d\-–\s]+лет?)", text, re.IGNORECASE)
    return match.group(1).strip() if match else None

def load_care_image(path_or_url: str | None) -> ImageReader | None:
    """Загружает и возвращает изображение инструкций по уходу.

    Parameters
    ----------
    path_or_url : str | None
        Путь к файлу или URL изображения.

    Returns
    -------
    :class:`ImageReader` | None
        Объект изображения или ``None`` при ошибке загрузки.
    """
    if not path_or_url:
        return None
    try:
        file_path = Path(path_or_url)
        if file_path.exists():
            img = Image.open(file_path).convert("RGB")
        else:
            response = requests.get(path_or_url, timeout=5)
            response.raise_for_status()
            img = Image.open(io.BytesIO(response.content)).convert("RGB")
        return ImageReader(img)
    except Exception:
        return None

def extract_other_attributes(meta: dict, exclude_keys: list[str], slug_to_label: dict[str, str]) -> str | None:
    """Формирует строку дополнительных атрибутов товара."""
    attributes = []
    translation = {
        "color": "Цвет",
        "uzor": "Узор",
        "patterns": "Узор",
        "material": "Материал",
        "type": "Тип",
        # при желании добавляй свои подписи
    }

    for key, value in meta.items():
        if key.startswith("attribute_") and key not in exclude_keys and value.strip():
            attr_key = key.replace("attribute_pa_", "").replace("attribute_", "").lower()
            translated_name = translation.get(attr_key, attr_key.capitalize())
            human_value = slug_to_label.get(value.strip(), value.strip())
            attributes.append(f"{translated_name}: {human_value}")

    return ", ".join(attributes) if attributes else None
    

def get_product_quantity(product: dict, use_stock_quantity: bool = True) -> int:
    """Возвращает количество этикеток, которое нужно напечатать."""
    try:
        if not use_stock_quantity:
            return 1
        meta = product.get('meta', {})
        raw_qty = meta.get('_stock', '1')
        return int(float(raw_qty)) if raw_qty else 1
    except Exception as e:
        logger.warning(f"[WARN] Ошибка при определении количества: {e}")
        return 1


class LabelGenerator:
    """\
    Класс для генерации PDF с этикетками.

    В конструктор передаются настройки из ``settings.json``. Все значения
    сохраняются как атрибуты экземпляра и используются при генерации.
    """

    def __init__(self, settings: dict, db_service: "DatabaseService"):
        # Сохраняем все параметры, конвертируя миллиметры в пункты
        self.page_width = settings.get("page_width_mm", DEFAULT_PAGE_WIDTH_MM) * mm
        self.page_height = settings.get("page_height_mm", DEFAULT_PAGE_HEIGHT_MM) * mm
        self.label_width = settings.get("label_width_mm", DEFAULT_LABEL_WIDTH_MM) * mm
        self.font_size = settings.get("font_size", DEFAULT_FONT_SIZE)
        self.min_line_height = settings.get("min_line_height_mm", DEFAULT_MIN_LINE_HEIGHT_MM) * mm
        self.barcode_height = settings.get("barcode_height_mm", DEFAULT_BARCODE_HEIGHT_MM) * mm
        self.bottom_margin = settings.get("bottom_margin_mm", DEFAULT_BOTTOM_MARGIN_MM) * mm
        self.top_margin = settings.get("top_margin_mm", DEFAULT_TOP_MARGIN_MM) * mm
        self.output_file = settings.get("output_file", DEFAULT_OUTPUT_FILE)
        self.care_image_path = settings.get("care_image_path", DEFAULT_CARE_IMAGE_PATH)
        self.labels_per_page = settings.get("labels_per_page", DEFAULT_LABELS_PER_PAGE)
        self.use_stock_quantity = settings.get("use_stock_quantity", True)

        # Экземпляр сервиса для работы с базой данных
        self.db_service = db_service

        # Ограничения высоты строки
        self.MIN_LINE_HEIGHT = self.min_line_height
        self.MAX_LINE_HEIGHT = 4.0 * mm

    def generate_labels(self, products: dict[int, dict]) -> None:
        """\
        Сформировать PDF из переданного набора товаров.

        Параметры
        ----------
        products : dict[int, dict]
            Словарь товаров, полученный из :meth:`DatabaseService.get_products_by_skus`.
        """
        # Подготавливаем canvas для рисования
        buffer = canvas.Canvas(self.output_file, pagesize=(self.page_width, self.page_height))

        # Однократно пробуем загрузить изображение инструкций по уходу
        care_img = load_care_image(self.care_image_path)

        products_list = list(products.values())

        # Собираем все slug-значения атрибутов для последующего перевода
        all_slugs = set()
        for product in products.values():
            for key, value in product['meta'].items():
                if key.startswith("attribute_") and value.strip():
                    all_slugs.add(value.strip())

        # Получаем человекочитаемые названия терминов через сервис базы данных
        slug_to_label = self.db_service.get_term_labels(all_slugs)

        for idx, product in enumerate(products_list):
            # Рассчитываем позицию этикетки на странице
            pos_in_page = idx % self.labels_per_page
            x = pos_in_page * self.label_width

            # При переходе на новую строку выводим новую страницу
            if pos_in_page == 0 and idx != 0:
                buffer.showPage()

            center_x = x + self.label_width / 2
            current_y = self.page_height - self.top_margin

            sku = product['meta'].get('_sku', 'N/A')
            price = (
                product['meta'].get('_price')
                or product['meta'].get('_regular_price')
                or product['meta'].get('_sale_price')
                or '0.00'
            )
            base_title = product.get('base_title', product['title'])
            description = product.get('content', '')

            # Определяем значение размера
            size_val = ""
            for key in ["attribute_pa_razmer", "attribute_pa_size", "attribute_pa_rost"]:
                if key in product['meta'] and product['meta'][key]:
                    size_val = product['meta'][key]
                    break
            if not size_val:
                size_val = extract_age_as_size(description)

            art_and_size = f"Арт: {sku}"

            def is_size_value(value: str) -> bool:
                # Проверяем, является ли значение именно размером
                if re.search(r"[A-Za-zА-Яа-я]", value):
                    return True
                if re.match(r"\d+\s*[\-–]\s*\d+", value):
                    return True
                try:
                    return int(value) < 56
                except ValueError:
                    return False

            size_attr_keys = ["attribute_pa_razmer", "attribute_pa_size", "attribute_pa_rost"]
            if size_val:
                label = "Размер" if is_size_value(size_val) else "Рост"
                art_and_size += f" {label}: {size_val}"

            other_attributes = extract_other_attributes(
                product['meta'], exclude_keys=size_attr_keys, slug_to_label=slug_to_label
            )
            if other_attributes:
                art_and_size += f", {other_attributes}"

            composition = extract_composition(description) or "____________________"
            manufacturer = (
                extract_manufacturer(description)
                or "____________________\n____________________\n____________________"
            )
            measurements = extract_measurements(description, size_val)

            lines_defs = [
                ("DejaVuSans-Bold", f"EAC {base_title}", "center"),
                ("DejaVuSans-Bold", art_and_size, "left"),
            ]

            if measurements:
                lines_defs.append(("DejaVuSans", measurements, "left"))

            lines_defs += [
                ("DejaVuSans", f"Состав: {composition}", "left"),
                (
                    "DejaVuSans",
                    "Импортер: ИП Анисимов Д.В., г. Брест, ул. Московская 247 кв. 68, УНП 291760554",
                    "left",
                ),
                ("DejaVuSans", f"Изготовитель: {manufacturer}", "left"),
                ("DejaVuSans", "Дата изготовления:______202_г.", "left"),
                ("DejaVuSans", "Рекомендации по уходу:", "left"),
                ("DejaVuSans-Bold", f"ЦЕНА: {price} руб", "left"),
            ]

            final_lines = []
            for (font, rawtext, align) in lines_defs:
                sublines = simpleSplit(rawtext, font, self.font_size, self.label_width - 8)
                for idx_sub, sline in enumerate(sublines):
                    is_care = ("уход" in rawtext.lower()) and (idx_sub == len(sublines) - 1)
                    is_price = ("цена:" in rawtext.lower()) and (idx_sub == len(sublines) - 1)
                    final_lines.append((font, sline, align, is_care, is_price))

            text_lines_count = len(final_lines)

            has_care_img = any(line[3] for line in final_lines) and care_img
            care_img_height = 4
            care_img_extra = 2

            has_barcode = any(line[4] for line in final_lines)
            bc_height = self.barcode_height / mm  # высота штрихкода в мм
            bc_extra = 2

            physically_used_mm = 0
            if has_care_img:
                physically_used_mm += care_img_height + care_img_extra
            if has_barcode:
                physically_used_mm += bc_height + bc_extra

            text_space_mm = (self.page_height - self.top_margin - self.bottom_margin) / mm - physically_used_mm
            if text_space_mm < 5:
                text_space_mm = 5
            text_space_pts = text_space_mm * mm

            if text_lines_count > 0:
                raw_line_height = text_space_pts / text_lines_count
                if raw_line_height < self.MIN_LINE_HEIGHT:
                    line_height = self.MIN_LINE_HEIGHT
                elif raw_line_height > self.MAX_LINE_HEIGHT:
                    line_height = self.MAX_LINE_HEIGHT
                else:
                    line_height = raw_line_height
            else:
                line_height = self.MIN_LINE_HEIGHT

            for (font, txt, align, is_care, is_price) in final_lines:
                font_to_use = font
                size_to_use = self.font_size

                if is_price:
                    current_y -= 3 * mm
                    font_to_use = "DejaVuSans-Bold"
                    size_to_use = 8

                buffer.setFont(font_to_use, size_to_use)

                if is_care and has_care_img:
                    # Рисуем заголовок "Рекомендации по уходу" и изображение
                    if align == "center":
                        buffer.drawCentredString(center_x, current_y, txt)
                    else:
                        buffer.drawString(x + 4, current_y, txt)

                    current_y -= 1 * mm  # небольшой отступ перед картинкой

                    img_height_pt = care_img_height * mm
                    current_y -= img_height_pt
                    buffer.drawImage(
                        care_img, x + 4, current_y, width=(self.label_width - 8), height=img_height_pt
                    )
                else:
                    if align == "center":
                        buffer.drawCentredString(center_x, current_y, txt)
                    else:
                        buffer.drawString(x + 4, current_y, txt)

                    current_y -= line_height

                if is_price and has_barcode:
                    barcode_height_mm = self.barcode_height / mm
                    left_right_padding_mm = 2

                    usable_width_mm = (self.label_width / mm) - 2 * left_right_padding_mm

                    bc = createBarcodeDrawing(
                        "Code128",
                        value=sku,
                        barHeight=barcode_height_mm * mm,
                        barWidth=1.2,
                        humanReadable=False,
                    )

                    bc_width = bc.width
                    scale_factor = (usable_width_mm * mm) / bc_width

                    bc_x = x + left_right_padding_mm * mm + (
                        (usable_width_mm * mm) - (bc_width * scale_factor)
                    ) / 2
                    bc_y = current_y - barcode_height_mm * mm

                    buffer.saveState()
                    buffer.translate(bc_x, bc_y)
                    buffer.scale(scale_factor, 1.0)
                    renderPDF.draw(bc, buffer, 0, 0)
                    buffer.restoreState()

        if len(products_list) % self.labels_per_page != 0:
            buffer.showPage()

        buffer.save()
        # Предупреждение о пути сгенерированного PDF-файла.
        logger.warning("Сгенерировано: %s", self.output_file)

    logger.debug("▶ Запуск генерации: %s", skus)
    def generate_labels_entry(self, skus: list[str]) -> None:
        """\
        Точка входа для генерации этикеток по списку SKU.

        Параметры
        ----------
        skus : list[str]
            Список артикулов, для которых нужно напечатать этикетки.
        Сервис БД передается через конструктор.
        """
        # Загружаем данные товаров из базы
        try:
            products = self.db_service.get_products_by_skus(skus)
        except DatabaseConnectionError as exc:
            # Ошибка подключения к БД отображается в логах.
            logger.error("[DB ERROR] %s", exc)
            return

        # Расширяем список товаров с учётом количества
        expanded_products: list[dict] = []
        for product in products.values():
            qty = get_product_quantity(product, self.use_stock_quantity)
            expanded_products.extend([product] * qty)

        mapping = {i: p for i, p in enumerate(expanded_products)}
        self.generate_labels(mapping)


def generate_labels_entry(skus, settings, db_config):
    """Высокоуровневая функция запуска генерации этикеток."""
    db_service = DatabaseService(db_config)
    generator = LabelGenerator(settings, db_service)
    try:
        generator.generate_labels_entry(skus)
    except DatabaseConnectionError as exc:
        # Логируем проблемы с подключением к БД при верхнеуровневом вызове.
        logger.error("[DB ERROR] %s", exc)

