from label_engine import generate_labels_entry
import tempfile, os
from pdf2image import convert_from_path

def render_preview(skus, settings, db_config, single=True):
    """
    Генерирует PNG превью: одной этикетки или страницы.
    Возвращает путь к PNG.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "preview.pdf")
        settings['output_file'] = pdf_path

        if single:
            skus = skus[:1]

        generate_labels_entry(skus, settings, db_config)

        images = convert_from_path(pdf_path, dpi=150)
        img_path = os.path.join(tmpdir, "preview.png")
        images[0].save(img_path, "PNG")
        return img_path  # Временный путь

def generate_preview_pdf(pdf_path, sku, settings, db_config, generator_func=generate_labels_entry):
    # Генерирует PDF с одной этикеткой
    generator_func([sku], settings, db_config)
    # Переименовываем файл, если необходимо
    output_file = settings.get("output_file", "labels.pdf")
    if os.path.exists(output_file):
        os.replace(output_file, pdf_path)

def convert_pdf_to_image(pdf_path):
    images = convert_from_path(pdf_path, dpi=150)
    return images[0] if images else None