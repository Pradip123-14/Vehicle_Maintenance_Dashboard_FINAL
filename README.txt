Vehicle Maintenance Invoice Dashboard - Star Motor extraction update

FOLDER CONTENTS
- Vehicle_Maintenance_Dashboard_App_FINAL.py : Streamlit app
- requirements.txt : Python packages
- Vehicle_Maintenance_Invoice_Output_Sample.xlsx : agreed output template/reference

RUN ON WINDOWS (Python 3.12)
1. Extract the ZIP to Desktop.
2. Open the extracted folder in File Explorer.
3. Click the address bar, type cmd, press Enter.
4. Run: py -3.12 -m pip install -r requirements.txt
5. Run: py -3.12 -m streamlit run Vehicle_Maintenance_Dashboard_App_FINAL.py
6. Open http://localhost:8501

STAR MOTOR WORKS UPDATE
The Star Motor parser now reads the HSN/SAC plus numeric columns from each numbered row, including wrapped item descriptions and the separate Services section. It was tested against the supplied Star Motor PDFs for bills 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 165 and 166. The tested extraction found item rows and line totals that sum to the printed grand totals for those supplied invoices.

IMPORTANT
Always review the generated Excel against the source PDF before posting to Tally. Other vendor formats and scanned documents may require manual review. OCR for scanned PDFs is not included by default; this app uses embedded PDF text.
