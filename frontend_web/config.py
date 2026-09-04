import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-cambiar-en-prod")
    API_URL = os.environ.get("API_URL", "http://localhost:8000/api/v1")
    USAR_FIXTURES = True          # False cuando exista la API real
    DATA_DIR = "app/data"