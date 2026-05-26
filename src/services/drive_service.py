import io
import os
import logging
import re
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload, MediaFileUpload
from src.core.google_client import google_manager
from src.config import Config
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class DriveService:
    def __init__(self):
        self.drive_service = google_manager.get_drive_service()
        self.output_folder_id = Config.DRIVE_OUTPUT_FOLDER_ID

    def extract_file_id(self, url: str) -> str:
        if not url: return None
        match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
        if match: return match.group(1)
        match = re.search(r'id=([a-zA-Z0-9_-]+)', url)
        if match: return match.group(1)
        return url 

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def create_google_doc(self, title: str, content: str, as_html: bool = True) -> str:
        try:
            logger.info(f"Creando Google Doc (Estético) '{title}'...")
            file_metadata = {
                'name': title,
                'mimeType': 'application/vnd.google-apps.document',
                'parents': [self.output_folder_id]
            }
            upload_mimetype = 'text/html' if as_html else 'text/plain'
            media = MediaIoBaseUpload(io.BytesIO(content.encode('utf-8')), mimetype=upload_mimetype, resumable=True)
            
            file = self.drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
            link = file.get('webViewLink')
            logger.info(f"Google Doc creado exitosamente: {link}")
            return link
        except Exception as e:
            logger.error(f"Error creando Google Doc: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def convert_local_docx_to_pdf(self, local_docx_path: str, output_pdf_path: str) -> str:
        try:
            logger.info(f"Convirtiendo DOCX a PDF vía motor de Drive: {os.path.basename(local_docx_path)}")
            file_metadata = {
                'name': 'Temp_Conversion_DOE',
                'mimeType': 'application/vnd.google-apps.document'
            }
            # CORRECCIÓN AQUÍ: Usar MediaFileUpload para rutas de archivos locales
            media = MediaFileUpload(
                local_docx_path, 
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document', 
                resumable=True
            )
            
            temp_file = self.drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            temp_file_id = temp_file.get('id')
            
            request = self.drive_service.files().export_media(fileId=temp_file_id, mimeType='application/pdf')
            os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
            
            with open(output_pdf_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
            
            self.drive_service.files().delete(fileId=temp_file_id).execute()
            logger.info(f"Conversión exitosa, PDF guardado en: {output_pdf_path}")
            return output_pdf_path
        except Exception as e:
            logger.error(f"Error convirtiendo DOCX a PDF: {e}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def download_drive_link_as_pdf(self, drive_link: str, output_pdf_path: str) -> str:
        file_id = self.extract_file_id(drive_link)
        if not file_id: return None
            
        try:
            logger.info(f"Descargando transcripción de Drive (ID: {file_id[:8]}...)")
            file_info = self.drive_service.files().get(fileId=file_id, fields='mimeType, name').execute()
            mime_type = file_info.get('mimeType')
            
            os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
            
            if mime_type == 'application/vnd.google-apps.document':
                request = self.drive_service.files().export_media(fileId=file_id, mimeType='application/pdf')
            else:
                request = self.drive_service.files().get_media(fileId=file_id)
            
            with open(output_pdf_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    
            if mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                temp_docx = output_pdf_path + ".docx"
                os.rename(output_pdf_path, temp_docx)
                self.convert_local_docx_to_pdf(temp_docx, output_pdf_path)
                if os.path.exists(temp_docx): os.remove(temp_docx)
                
            return output_pdf_path
        except Exception as e:
            logger.error(f"Error descargando archivo de Drive: {e}")
            return None

drive_service = DriveService()