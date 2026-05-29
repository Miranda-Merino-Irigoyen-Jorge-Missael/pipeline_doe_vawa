import os
import logging
import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from src.config import Config

logger = logging.getLogger(__name__)

class GoogleClientManager:
    """
    Maneja las conexiones autenticadas a Google usando OAuth 2.0.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GoogleClientManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._oauth_creds = None
        self._drive_service = None
        self._sheets_client = None
        self._docs_service = None 
        self._initialized = True

    def _get_oauth_creds(self):
        """Carga o genera las credenciales OAuth (token.json)."""
        if not self._oauth_creds:
            try:
                # 1. Intentar cargar el token existente
                if os.path.exists(Config.TOKEN_FILE):
                    self._oauth_creds = Credentials.from_authorized_user_file(
                        Config.TOKEN_FILE, Config.OAUTH_SCOPES
                    )
                    
                    # Si expiró, refrescarlo
                    if self._oauth_creds and self._oauth_creds.expired and self._oauth_creds.refresh_token:
                        self._oauth_creds.refresh(Request())
                        with open(Config.TOKEN_FILE, 'w') as token:
                            token.write(self._oauth_creds.to_json())
                    elif not self._oauth_creds.valid:
                        self._oauth_creds = None

                # 2. Si no hay token válido, iniciar flujo de login en el navegador
                if not self._oauth_creds:
                    if not os.path.exists(Config.OAUTH_CREDENTIALS_FILE):
                        raise FileNotFoundError(
                            f"Falta el archivo client_secret: {Config.OAUTH_CREDENTIALS_FILE}"
                        )
                    
                    flow = InstalledAppFlow.from_client_secrets_file(
                        Config.OAUTH_CREDENTIALS_FILE, 
                        Config.OAUTH_SCOPES
                    )
                    self._oauth_creds = flow.run_local_server(port=0)
                    
                    # Guardar el token para la próxima vez
                    with open(Config.TOKEN_FILE, 'w') as token:
                        token.write(self._oauth_creds.to_json())
                        
            except Exception as e:
                logger.error(f"Error en autenticación OAuth: {e}")
                raise
                
        return self._oauth_creds

    def get_drive_service(self):
        """Retorna el cliente de Google Drive API v3."""
        if not self._drive_service:
            creds = self._get_oauth_creds()
            self._drive_service = build('drive', 'v3', credentials=creds)
        return self._drive_service

    def get_sheets_client(self):
        """Retorna el cliente de gspread para manipular la hoja de cálculo."""
        if not self._sheets_client:
            creds = self._get_oauth_creds()
            self._sheets_client = gspread.authorize(creds)
        return self._sheets_client

    @property
    def docs_service(self):
        """Retorna el cliente de Google Docs API v1 (Requerido para modificar Tabs)."""
        if not self._docs_service:
            creds = self._get_oauth_creds()
            self._docs_service = build('docs', 'v1', credentials=creds)
        return self._docs_service

    # === NUEVOS MÉTODOS PARA MANEJO DE PESTAÑAS (TABS) ===
    def get_document_with_tabs(self, document_id):
        """
        Recupera un documento asegurando que devuelva el contenido de todas las pestañas.
        """
        doc = self.docs_service.documents().get(
            documentId=document_id,
            includeTabsContent=True
        ).execute()
        return doc

    def get_tab_id_by_index(self, document_id, tab_index=0):
        """
        Obtiene el tabId de una pestaña específica basándose en su índice.
        """
        doc = self.get_document_with_tabs(document_id)
        tabs = doc.get('tabs', [])
        
        if len(tabs) > tab_index:
            return tabs[tab_index].get('tabProperties', {}).get('tabId')
        return None

# Instancia global para importar en todo el proyecto
google_manager = GoogleClientManager()