from label_engine import generate_labels_entry
from database_service import DatabaseConnectionError
import tempfile, os
from pdf2image import convert_from_path
import logging

# Логгер модуля для вывода ошибок при генерации превью.
logger = logging.getLogger(__name__)

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

def generate_preview_pdf(pdf_path, skus, settings, db_config, generator_func=generate_labels_entry):
    """Generate a PDF preview for the provided SKUs.

    Parameters
    ----------
    pdf_path : str
        Destination path for the preview PDF.
    skus : Iterable[str] | str
        Collection of SKUs or a single SKU string.
    settings : dict
        Label generation settings. ``output_file`` will be temporarily
        overridden with ``pdf_path``.
    db_config : dict
        Database connection parameters.
    generator_func : Callable
        Function used to generate labels. Defaults to
        :func:`generate_labels_entry`.
    """

    if isinstance(skus, str):
        sku_list = [skus]
    else:
        sku_list = list(skus)

    # Save original output file and override it with the preview path.
    original_output = settings.get("output_file")
    settings["output_file"] = pdf_path

    try:
        generator_func(sku_list, settings, db_config)
    except DatabaseConnectionError as exc:
        # Выводим ошибку подключения к базе данных при формировании превью.
        logger.error("[DB ERROR] %s", exc)
    finally:
        # Restore the original output_file setting if it existed.
        if original_output is not None:
            settings["output_file"] = original_output
        else:
            settings.pop("output_file", None)

def convert_pdf_to_image(pdf_path):
    """Convert the first page of a PDF to a PIL image."""
    images = convert_from_path(pdf_path, dpi=150)
    return images[0] if images else None
