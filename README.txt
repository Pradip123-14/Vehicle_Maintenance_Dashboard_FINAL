
# Vehicle Maintenance Invoice Dashboard

A Python and Streamlit application for extracting and reviewing vehicle maintenance invoice information.

## Features
- Upload supported invoice PDFs.
- Extract invoice information from embedded PDF text.
- Review extracted details and totals.
- Generate Excel output for further review.

## Requirements
- Python 3.12
- Streamlit
- Pandas
- OpenPyXL
- PyMuPDF
- Pillow

## Run locally

Install the dependencies:

```bash
python -m pip install -r requirements.txt
```

Start the dashboard:

```bash
python -m streamlit run Vehicle_Maintenance_Dashboard_App_FINAL.py
```

Open http://localhost:8501 in your browser.

## Notes
- Scanned PDF OCR is not included by default.
- Verify extracted invoice information against the source invoice before using it for accounting.
- Do not upload confidential invoices or business data to a public repository.
item rows and line totals that sum to the printed grand totals for those supplied invoices.

IMPORTANT
Always review the generated Excel against the source PDF before posting to Tally. Other vendor formats and scanned documents may require manual review. OCR for scanned PDFs is not included by default; this app uses embedded PDF text.
