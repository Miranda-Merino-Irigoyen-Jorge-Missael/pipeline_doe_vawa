import logging
import dropbox
from dropbox.exceptions import ApiError
from src.config import Config

logger = logging.getLogger(__name__)

class DropboxService:
    """
    Servicio para interactuar con enlaces de Dropbox.
    Por ahora (Fase 1), solo se encarga de validar que el enlace exista y sea accesible.
    """
    def __init__(self):
        token = Config.DROPBOX_TOKEN
        # Solo inicializamos el cliente si el token existe en el .env
        self.dbx = dropbox.Dropbox(token) if token else None

    def validate_link(self, shared_link: str) -> bool:
        """
        Verifica que el link de la carpeta o archivo de Dropbox es válido y público/accesible.
        """
        # Si el link está vacío o es muy corto, lo rechazamos rápido
        if not shared_link or len(shared_link) < 10:
            logger.warning("El link de Dropbox está vacío o es inválido.")
            return False
            
        if not self.dbx:
            logger.warning("No se ha configurado DROPBOX_TOKEN en el .env. Saltando validación estricta.")
            return True # Devolvemos True para no bloquear el flujo si aún no configuras Dropbox
            
        try:
            logger.info("Validando enlace de Dropbox...")
            # Intentamos obtener la metadata del link compartido
            self.dbx.sharing_get_shared_link_metadata(url=shared_link)
            logger.info("Enlace de Dropbox validado correctamente.")
            return True
            
        except ApiError as e:
            logger.error(f"Error de API al validar link de Dropbox (¿Link roto o privado?): {e}")
            return False
        except Exception as e:
            logger.error(f"Error inesperado validando Dropbox: {e}")
            return False

# Instancia global
dropbox_service = DropboxService()