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
import mysql.connector
import json
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.graphics import renderPDF
from pathlib import Path

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
pdfmetrics.registerFont(TTFont("DejaVuSans", "fonts/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", "fonts/DejaVuSans-Bold.ttf"))

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def extract_composition(text):
    match = re.search(r"Состав:([^\n\r]*)", text, re.IGNORECASE)
    return match.group(1).strip() if match else None

def extract_manufacturer(text):
    match = re.search(r"(?:Адрес изготовления|Адрес производителя|Адрес производитель):([^\n\r]*)", text, re.IGNORECASE)
    return match.group(1).strip() if match else None

def extract_measurements(text, target_size):
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

def write_measurement_log(log_lines):
    with open("measurements.log", "a", encoding="utf-8") as log:
        log.writelines(log_lines)

def extract_age_as_size(text):
    match = re.search(r"Возраст:?\s*([\d\-–\s]+лет?)", text, re.IGNORECASE)
    return match.group(1).strip() if match else None

def load_care_image(path_or_url):
    """Return :class:`ImageReader` from local file or URL if possible."""
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
    
def extract_other_attributes(meta, exclude_keys, slug_to_label):
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
    
def get_term_labels(term_slugs, db_config):
    """Return mapping slug -> human label."""
    if not term_slugs:
        return {}

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    format_strings = ','.join(['%s'] * len(term_slugs))
    query = f"SELECT slug, name FROM wp_terms WHERE slug IN ({format_strings})"
    cursor.execute(query, list(term_slugs))

    result = {slug: name for slug, name in cursor.fetchall()}
    
    cursor.close()
    conn.close()
    return result

# === ПОДКЛЮЧЕНИЕ К БД ===
def get_products_by_skus(skus, db_config):
    """Fetch product data for the given SKUs."""
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)

    format_strings = ','.join(['%s'] * len(skus))
    query = f"""
        SELECT p.ID, p.post_title, p.post_parent, pm.meta_key, pm.meta_value
        FROM wp_posts p
        JOIN wp_postmeta pm ON p.ID = pm.post_id
        WHERE (pm.meta_key IN ('_sku', '_price', '_regular_price', '_sale_price', '_product_attributes', '_variation_description', '_stock')
               OR pm.meta_key LIKE 'attribute_%')
        AND p.post_type = 'product_variation'
        AND pm.post_id IN (
            SELECT post_id FROM wp_postmeta WHERE meta_key = '_sku' AND meta_value IN ({format_strings})
        )
    """
    cursor.execute(query, skus)

    products = {}
    parent_ids = set()
    for row in cursor.fetchall():
        pid = row['ID']
        if pid not in products:
            products[pid] = {
                'id': pid,
                'parent': row['post_parent'],
                'meta': {},
                'title': row['post_title']
            }
        products[pid]['meta'][row['meta_key']] = row['meta_value']
        parent_ids.add(row['post_parent'])

    # Получаем названия родительских товаров
    if parent_ids:
        parent_query = f"SELECT ID, post_title, post_content FROM wp_posts WHERE ID IN ({','.join(map(str, parent_ids))})"
        cursor.execute(parent_query)
        parents = {row['ID']: {'title': row['post_title'], 'content': row['post_content']} for row in cursor.fetchall()}
        for p in products.values():
            parent = parents.get(p['parent'])
            if parent:
                p['base_title'] = parent['title']
                p['content'] = parent['content']

    cursor.close()
    conn.close()
    return products


def get_product_quantity(product, use_stock_quantity=True):
    """Return how many labels should be printed for a product."""
    if not use_stock_quantity:
        return 1
    raw_qty = product['meta'].get('_stock', '1')
    try:
        return int(float(raw_qty)) if raw_qty else 1
    except ValueError:
        return 1


class LabelGenerator:
    """\
    Класс для генерации PDF с этикетками.

    В конструктор передаются настройки из ``settings.json``. Все значения
    сохраняются как атрибуты экземпляра и используются при генерации.
    """

    def __init__(self, settings: dict):
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

        # Ограничения высоты строки
        self.MIN_LINE_HEIGHT = self.min_line_height
        self.MAX_LINE_HEIGHT = 4.0 * mm

    def generate_labels(self, products: dict[int, dict], db_config: dict) -> None:
        """\
        Сформировать PDF из переданного набора товаров.

        Параметры
        ----------
        products : dict[int, dict]
            Словарь товаров, полученный из :func:`get_products_by_skus`.
        db_config : dict
            Параметры подключения к базе данных.
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

        slug_to_label = get_term_labels(all_slugs, db_config)

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
        print(f"Сгенерировано: {self.output_file}")

    def generate_labels_entry(self, skus: list[str], db_config: dict) -> None:
        """\
        Точка входа для генерации этикеток по списку SKU.

        Параметры
        ----------
        skus : list[str]
            Список артикулов, для которых нужно напечатать этикетки.
        db_config : dict
            Параметры подключения к базе данных.
        """
        # Загружаем данные товаров из базы
        products = get_products_by_skus(skus, db_config)

        # Расширяем список товаров с учётом количества
        expanded_products: list[dict] = []
        for product in products.values():
            qty = get_product_quantity(product, self.use_stock_quantity)
            expanded_products.extend([product] * qty)

        mapping = {i: p for i, p in enumerate(expanded_products)}
        self.generate_labels(mapping, db_config)


def generate_labels_entry(skus, settings, db_config):
    """Высокоуровневая функция для совместимости с существующим кодом."""
    generator = LabelGenerator(settings)
    generator.generate_labels_entry(skus, db_config)

