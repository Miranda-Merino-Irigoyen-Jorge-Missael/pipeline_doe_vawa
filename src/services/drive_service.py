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
        match = re.search(r'/folders/([a-zA-Z0-9_-]+)', url)
        if match: return match.group(1)
        match = re.search(r'id=([a-zA-Z0-9_-]+)', url)
        if match: return match.group(1)
        return url 

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def copy_template(self, template_id: str, new_title: str) -> tuple:
        """
        NUEVO: Copia un documento existente en Drive (tu plantilla con pestañas)
        y lo guarda en la carpeta de output con el nombre del cliente.
        Retorna una tupla: (document_id, webViewLink)
        """
        try:
            logger.info(f"Copiando plantilla base para crear: '{new_title}'...")
            body = {
                'name': new_title,
                'parents': [self.output_folder_id]
            }
            # Se usa el método copy de la API de Drive
            copied_file = self.drive_service.files().copy(
                fileId=template_id,
                body=body,
                fields='id, webViewLink'
            ).execute()
            
            doc_id = copied_file.get('id')
            link = copied_file.get('webViewLink')
            
            logger.info(f"[✓] Documento base creado a partir de plantilla: {link}")
            return doc_id, link
        except Exception as e:
            logger.error(f"Error copiando la plantilla de Google Docs: {e}")
            raise

    # === MÉTODOS ANTERIORES INTACTOS ===

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def create_google_doc(self, title: str, content: str, as_html: bool = True) -> str:
        # Lo conservamos por si lo necesitas en otro proyecto, aunque ya no lo usaremos aquí.
        try:
            file_metadata = {
                'name': title,
                'mimeType': 'application/vnd.google-apps.document',
                'parents': [self.output_folder_id]
            }
            upload_mimetype = 'text/html' if as_html else 'text/plain'
            media = MediaIoBaseUpload(io.BytesIO(content.encode('utf-8')), mimetype=upload_mimetype, resumable=True)
            
            file = self.drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
            return file.get('webViewLink')
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
    def download_drive_link_as_pdf(self, drive_link: str, output_base_path: str) -> str:
        base_path, _ = os.path.splitext(output_base_path)
        file_id = self.extract_file_id(drive_link)
        if not file_id: return None
            
        try:
            file_info = self.drive_service.files().get(fileId=file_id, fields='mimeType, name').execute()
            mime_type = file_info.get('mimeType')
            
            os.makedirs(os.path.dirname(base_path), exist_ok=True)
            
            if mime_type == 'application/vnd.google-apps.document':
                final_path = base_path + ".txt"
                request = self.drive_service.files().export_media(fileId=file_id, mimeType='text/plain')
            else:
                final_path = base_path + ".pdf"
                request = self.drive_service.files().get_media(fileId=file_id)
            
            with open(final_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    
            if mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                temp_docx = base_path + ".docx"
                os.rename(final_path, temp_docx)
                final_pdf = base_path + ".pdf"
                self.convert_local_docx_to_pdf(temp_docx, final_pdf)
                if os.path.exists(temp_docx): os.remove(temp_docx)
                return final_pdf
                
            return final_path
        except Exception as e:
            logger.error(f"Error descargando archivo de Drive: {e}")
            return None

    def download_folder_contents(self, folder_url: str, download_dir: str) -> list:
        folder_id = self.extract_file_id(folder_url)
        if not folder_id: return []
        
        downloaded_files = []
        try:
            file_info = self.drive_service.files().get(fileId=folder_id, fields='mimeType, name').execute()
            
            if file_info.get('mimeType') != 'application/vnd.google-apps.folder':
                base_path = os.path.join(download_dir, file_info.get('name').replace(" ", "_"))
                ruta = self.download_drive_link_as_pdf(folder_url, base_path)
                return [ruta] if ruta else []
                
            os.makedirs(download_dir, exist_ok=True)
            query = f"'{folder_id}' in parents and trashed = false"
            results = self.drive_service.files().list(q=query, fields="nextPageToken, files(id, name, mimeType)").execute()
            items = results.get('files', [])
            
            if not items: return []
                
            for item in items:
                mime = item['mimeType']
                if mime == 'application/vnd.google-apps.folder': continue
                
                safe_name = item['name'].replace(" ", "_")
                base_name, _ = os.path.splitext(safe_name)
                
                if mime == 'application/vnd.google-apps.document':
                    file_path = os.path.join(download_dir, base_name + '.txt')
                    request = self.drive_service.files().export_media(fileId=item['id'], mimeType='text/plain')
                    with open(file_path, 'wb') as f:
                        downloader = MediaIoBaseDownload(f, request)
                        done = False
                        while not done: _, done = downloader.next_chunk()
                    downloaded_files.append(file_path)

                elif mime == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                    local_docx = os.path.join(download_dir, base_name + '.docx')
                    request = self.drive_service.files().get_media(fileId=item['id'])
                    with open(local_docx, 'wb') as f:
                        downloader = MediaIoBaseDownload(f, request)
                        done = False
                        while not done: _, done = downloader.next_chunk()
                    
                    pdf_path = os.path.join(download_dir, base_name + '.pdf')
                    ruta = self.convert_local_docx_to_pdf(local_docx, pdf_path)
                    if ruta: downloaded_files.append(ruta)

                elif mime == 'application/pdf':
                    file_path = os.path.join(download_dir, base_name + '.pdf')
                    request = self.drive_service.files().get_media(fileId=item['id'])
                    with open(file_path, 'wb') as f:
                        downloader = MediaIoBaseDownload(f, request)
                        done = False
                        while not done: _, done = downloader.next_chunk()
                    downloaded_files.append(file_path)
                    
            return downloaded_files
        except Exception as e:
            logger.error(f"Error explorando carpeta de Google Drive: {e}")
            return downloaded_files

drive_service = DriveService()