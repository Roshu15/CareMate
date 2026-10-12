# Legacy command-line utilities

These scripts were kept from the earlier prototype so their code remains available. The running web app does not use them for normal requests; its API and reminder worker live in `backend/`.

Run scripts from the `CareMate_ocr` project directory, for example:

```powershell
py scripts/legacy/adherence.py
py scripts/legacy/process_prescription.py
```

Some scripts read or write `caremate.db`. Back up that database before running legacy utilities. The prescription script requires `OCR_SPACE_API_KEY` and may save an unassigned medicine record, so use the web UI for normal prescription entry.
