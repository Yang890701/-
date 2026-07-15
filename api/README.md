# API Scaffold

Target runtime: Python 3.12 or 3.13.

Create a virtual environment before installing dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The only implemented endpoint in T1 is:

```text
GET /health -> {"status":"ok"}
```
