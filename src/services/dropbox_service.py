import os
import logging
import re
import requests
import dropbox
from dropbox.exceptions import ApiError
from dropbox.files import SharedLink
from src.config import Config

logger = logging.getLogger(__name__)

class DropboxService:
    def __init__(self):
        token = Config.DROPBOX_TOKEN
        self.dbx = dropbox.Dropbox(token) if token else None

    def _build_direct_download_url(self, shared_link: str) -> str:
        """Convierte un enlace compartido de Dropbox a URL de descarga directa (dl=1)."""
        url = re.sub(r'([?&])dl=0', r'\1dl=1', shared_link)
        if 'dl=1' not in url:
            url += ('&dl=1' if '?' in url else '?dl=1')
        return url

    def _download_via_direct_url(self, shared_link: str, download_path: str) -> str:
        """Fallback HTTP: regenera el link de Dropbox (dl=1) y descarga sin SDK."""
        try:
            direct_url = self._build_direct_download_url(shared_link)
            logger.info(f"Regenerando link de Dropbox para descarga directa: {direct_url}")
            response = requests.get(direct_url, timeout=120, allow_redirects=True)
            response.raise_for_status()
            os.makedirs(os.path.dirname(download_path), exist_ok=True)
            with open(download_path, "wb") as f:
                f.write(response.content)
            logger.info(f"Archivo descargado via URL directa: {download_path}")
            return download_path
        except Exception as e:
            logger.error(f"Error en descarga directa HTTP: {e}")
            return None

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
            if "missing '.tag' key" in str(e) or "link_permissions" in str(e):
                logger.info("Intentando fallback: regenerando link de Dropbox...")
                return self._download_via_direct_url(shared_link, download_path)
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
                    try:
                        _, response = self.dbx.sharing_get_shared_link_file(url=folder_url, path="/" + entry.name)
                        with open(file_path, "wb") as f:
                            f.write(response.content)
                        downloaded_files.append(file_path)
                    except Exception as file_err:
                        logger.error(f"Error descargando {entry.name}: {file_err}")
                        if "missing '.tag' key" in str(file_err) or "link_permissions" in str(file_err):
                            logger.info(f"Intentando fallback HTTP para {entry.name}...")
                            # Construir URL directa para el archivo dentro de la carpeta
                            direct_url = self._build_direct_download_url(folder_url)
                            # Dropbox acepta ?dl=1 con el path del archivo vía parámetro extra
                            file_direct_url = direct_url.rstrip('&') + f"&subfolder_nav_target={entry.path_lower}" if hasattr(entry, 'path_lower') else direct_url
                            result = self._download_via_direct_url(folder_url.replace('dl=0', 'dl=1').replace('scl/fo', 'scl/fo'), file_path)
                            if result:
                                downloaded_files.append(result)
                    
            logger.info(f"Se descargaron {len(downloaded_files)} archivos de la carpeta.")
            return downloaded_files
            
        except Exception as e:
            logger.error(f"Error explorando/descargando enlace de Dropbox: {e}")
            return downloaded_files

dropbox_service = DropboxService()