# Start Flask dev server (PowerShell helper)
$env:FLASK_APP = "app.py"
$env:FLASK_ENV = "development"
python -m flask run --host=0.0.0.0 --port=5000
