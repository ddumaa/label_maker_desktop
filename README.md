# label_maker_desktop

Desktop application for generating product labels using PyQt5 and ReportLab.

## Installation

1. Ensure you have Python installed.
2. Install dependencies by running the provided helper script **before the first launch**:

```bash
python install_dependencies.py
```

3. pdf2image requires Poppler. Install it via your package manager (e.g., `apt-get install poppler-utils`).

The application settings are stored in `settings.json` and database
configuration in `db_config.json`.

### Database configuration

Create a `db_config.json` file based on `db_config.example.json` with your
connection details. Optional keys allow tuning connection behaviour:

* `persistent` – keep a single connection open between queries.
* `pool_size` – size of the MySQL connection pool (if > 0).
* `max_retries` – how many times to retry connecting on transient errors.

## Running

Execute the GUI with:

```bash
python main.py
```
