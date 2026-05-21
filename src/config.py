import os
from pathlib import Path
from dotenv import load_dotenv

class Config:
    """Configuración centralizada del pipeline DOE VAWA."""
    
    # 1. Rutas Base
    BASE_DIR = Path(__file__).resolve().parent.parent
    
    # Cargar variables de entorno
    load_dotenv(BASE_DIR / ".env")

    # Archivos de credenciales OAuth
    OAUTH_CREDENTIALS_FILE = BASE_DIR / os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "client_secret.json")
    TOKEN_FILE = BASE_DIR / os.getenv("GOOGLE_OAUTH_TOKEN", "token.json")

    # 2. Configuración Vertex AI
    PROJECT_ID = os.getenv("PROJECT_ID")
    LOCATION = os.getenv("LOCATION", "us-east5")
    
    # 3. Configuración Sheets y Drive
    SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
    SHEET_NAME = os.getenv("SHEET_NAME")
    DRIVE_OUTPUT_FOLDER_ID = os.getenv("DRIVE_OUTPUT_FOLDER_ID")
    
    # 4. Configuración Dropbox
    DROPBOX_TOKEN = os.getenv("DROPBOX_TOKEN")

    # 5. Permisos (Scopes) para Google
    OAUTH_SCOPES = [
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/spreadsheets'
    ]

    @classmethod
    def validate(cls):
        """Valida que las variables críticas existan antes de arrancar."""
        missing = []
        if not cls.PROJECT_ID: missing.append("PROJECT_ID")
        if not cls.SPREADSHEET_ID: missing.append("SPREADSHEET_ID")
        
        if missing:
            raise ValueError(f"Faltan variables críticas en el .env: {', '.join(missing)}")

# Ejecutamos la validación al importar
Config.validate()