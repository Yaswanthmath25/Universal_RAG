
from pathlib import Path
import csv
from docx import Document


def extract_pdf(file_path):
    """Extract text from each PDF page."""
    import pymupdf

    extracted_data = []
    pdf = pymupdf.open(file_path)

    for page_number, page in enumerate(pdf, start=1):
        text = page.get_text().strip()

        if text:
            extracted_data.append({
                "page_number": page_number,
                "text": text
            })

    pdf.close()
    return extracted_data


def extract_docx(file_path):
    """Extract text from a Word document."""

    document = Document(file_path)

    text = "\n".join(
        paragraph.text
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    )

    return [{
        "page_number": None,
        "text": text
    }] if text else []


def extract_txt(file_path):
    """Extract text from a TXT file."""

    with open(file_path, "r", encoding="utf-8-sig") as file:
        text = file.read().strip()

    return [{
        "page_number": None,
        "text": text
    }] if text else []


def extract_csv(file_path):
    """Extract CSV rows as readable text."""

    extracted_data = []

    with open(file_path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames:
            return []

        for row_number, row in enumerate(reader, start=1):

            row_text = "\n".join(
                f"{column}: {value.strip() if value else 'Not available'}"
                for column, value in row.items()
                if column
            )

            if row_text.strip():
                extracted_data.append({
                    "page_number": None,
                    "row_number": row_number,
                    "text": row_text
                })

    return extracted_data


def extract_excel(file_path):
    """Extract data from all Excel sheets."""
    import pandas as pd

    extracted_data = []

    excel_file = pd.ExcelFile(file_path)

    for sheet_name in excel_file.sheet_names:

        dataframe = pd.read_excel(
            excel_file,
            sheet_name=sheet_name,
            dtype=str
        )

        dataframe = dataframe.fillna("Not available")

        for row_number, row in enumerate(
            dataframe.to_dict(orient="records"),
            start=1
        ):

            row_text = "\n".join(
                f"{column}: {value}"
                for column, value in row.items()
            )

            if row_text.strip():
                extracted_data.append({
                    "page_number": None,
                    "sheet_name": sheet_name,
                    "row_number": row_number,
                    "text": row_text
                })

    return extracted_data


def extract_document_text(file_path):
    """Identify document type and extract its text."""

    extension = Path(file_path).suffix.lower()

    if extension == ".pdf":
        return extract_pdf(file_path)

    elif extension == ".docx":
        return extract_docx(file_path)

    elif extension == ".txt":
        return extract_txt(file_path)

    elif extension == ".csv":
        return extract_csv(file_path)

    elif extension == ".xlsx":
        return extract_excel(file_path)

    else:
        raise ValueError("Unsupported document format")
