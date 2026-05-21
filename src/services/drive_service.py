import io
import logging
from googleapiclient.http import MediaIoBaseUpload
from src.core.google_client import google_manager
from src.config import Config
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class DriveService:
    """
    Servicio para manejar la creación de Google Docs en la carpeta de destino.
    """
    def __init__(self):
        self.drive_service = google_manager.get_drive_service()
        self.output_folder_id = Config.DRIVE_OUTPUT_FOLDER_ID

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def create_google_doc(self, title, content):
        """
        Crea un Google Doc en la carpeta especificada subiendo texto plano
        y pidiéndole a Drive que lo convierta nativamente.
        Devuelve el link para verlo/editarlo.
        """
        try:
            logger.info(f"Creando Google Doc '{title}'...")
            
            # Metadata: Le decimos a Google Drive que queremos un Google Doc nativo
            file_metadata = {
                'name': title,
                'mimeType': 'application/vnd.google-apps.document',
                'parents': [self.output_folder_id]
            }
            
            # Convertimos el texto (string) en un flujo de bytes para subirlo
            media = MediaIoBaseUpload(
                io.BytesIO(content.encode('utf-8')), 
                mimetype='text/plain', 
                resumable=True
            )
            
            # Ejecutamos la petición de creación
            file = self.drive_service.files().create(
                body=file_metadata, 
                media_body=media, 
                fields='id, webViewLink'
            ).execute()
            
            link = file.get('webViewLink')
            logger.info(f"Google Doc creado exitosamente: {link}")
            
            return link
            
        except Exception as e:
            logger.error(f"Error creando Google Doc: {e}")
            raise

# Instancia global para importar en el orquestador
drive_service = DriveService()