import os
import logging
import dropbox
from dropbox.exceptions import ApiError
from dropbox.files import SharedLink
from src.config import Config

logger = logging.getLogger(__name__)

class DropboxService:
    def __init__(self):
        token = Config.DROPBOX_TOKEN
        self.dbx = dropbox.Dropbox(token) if token else None

    def validate_link(self, shared_link: str) -> bool:
        if not shared_link or len(shared_link) < 10: return False
        if not self.dbx: return True 
        try:
            self.dbx.sharing_get_shared_link_metadata(url=shared_link)
            return True
        except Exception as e:
            return False

    def download_from_shared_link(self, shared_link: str, download_path: str) -> str:
        if not self.dbx: return None
        try:
            logger.info(f"Descargando archivo individual desde: {shared_link}")
            metadata, response = self.dbx.sharing_get_shared_link_file(url=shared_link)
            os.makedirs(os.path.dirname(download_path), exist_ok=True)
            with open(download_path, "wb") as f:
                f.write(response.content)
            logger.info(f"Archivo descargado exitosamente: {download_path}")
            return download_path
        except Exception as e:
            logger.error(f"Error descargando archivo de Dropbox: {e}")
            return None

    def download_folder_contents(self, folder_url: str, download_dir: str) -> list:
        if not self.dbx: return []
        downloaded_files = []
        try:
            logger.info(f"Explorando enlace de Dropbox: {folder_url}")
            
            # MAGIA AQUÍ: Verificamos primero si es una carpeta o un archivo suelto
            metadata = self.dbx.sharing_get_shared_link_metadata(url=folder_url)
            
            # Si resulta ser un solo archivo (ej. alguien pegó un PDF en vez de una carpeta)
            if isinstance(metadata, dropbox.sharing.FileLinkMetadata):
                logger.info(f"El enlace es de un archivo individual ({metadata.name}), no de una carpeta. Descargando...")
                file_path = os.path.join(download_dir, metadata.name)
                # Reutilizamos la otra función
                ruta = self.download_from_shared_link(folder_url, file_path)
                return [ruta] if ruta else []

            # Si es efectivamente una carpeta, procedemos normalmente
            shared_link = SharedLink(url=folder_url)
            res = self.dbx.files_list_folder(path="", shared_link=shared_link)
            os.makedirs(download_dir, exist_ok=True)
            
            for entry in res.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    file_path = os.path.join(download_dir, entry.name)
                    logger.info(f"Descargando documento de evidencia: {entry.name}...")
                    _, response = self.dbx.sharing_get_shared_link_file(url=folder_url, path="/" + entry.name)
                    with open(file_path, "wb") as f:
                        f.write(response.content)
                    downloaded_files.append(file_path)
                    
            logger.info(f"Se descargaron {len(downloaded_files)} archivos de la carpeta.")
            return downloaded_files
            
        except Exception as e:
            logger.error(f"Error explorando/descargando enlace de Dropbox: {e}")
            return downloaded_files

dropbox_service = DropboxService()