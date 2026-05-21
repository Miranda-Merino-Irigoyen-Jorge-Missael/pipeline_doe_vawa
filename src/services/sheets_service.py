import logging
from src.core.google_client import google_manager
from src.config import Config
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class SheetsService:
    """
    Servicio para leer y actualizar la hoja de control de la Fase 1.
    """
    
    # Mapeo de columnas (Índice base 1 para gspread)
    COL_CLIENT_NAME = 1    # A: Nombre del cliente
    COL_COLLABORATOR = 2   # B: Colaborador
    COL_DRIVE_LINK = 3     # C: Link Drive
    COL_DBX_LINK = 4       # D: Link Dropbox
    COL_COMMENTS = 5       # E: COMENTARIOS PARA CLAUDE
    COL_STATUS = 6         # F: STATUS
    COL_OUTPUT_LINK = 7    # G: Entregable (Doc)

    def __init__(self):
        self.client = google_manager.get_sheets_client()
        self.spreadsheet_id = Config.SPREADSHEET_ID
        self.sheet_name = Config.SHEET_NAME
        self._sheet = None

    @property
    def sheet(self):
        """Carga la hoja solo cuando se necesita (Lazy load)."""
        if not self._sheet:
            try:
                sh = self.client.open_by_key(self.spreadsheet_id)
                self._sheet = sh.worksheet(self.sheet_name)
            except Exception as e:
                logger.error(f"Error conectando a Sheet '{self.sheet_name}': {e}")
                raise
        return self._sheet

    def get_pending_rows(self):
        """
        Busca todas las filas cuyo STATUS (Col F) sea 'PENDING PROCESS'.
        """
        rows_data = []
        try:
            all_values = self.sheet.get_all_values()
            
            for i, row in enumerate(all_values):
                row_idx = i + 1  # gspread usa índices que empiezan en 1
                if row_idx == 1: 
                    continue # Saltamos la fila 1 (encabezados)

                # Nos aseguramos de que la fila tenga suficientes columnas para leer el status
                if len(row) >= self.COL_STATUS:
                    status = row[self.COL_STATUS - 1].strip()
                    
                    if status == 'PENDING PROCESS':
                        row_data = {
                            'row_idx': row_idx,
                            'client_name': row[self.COL_CLIENT_NAME - 1] if len(row) >= self.COL_CLIENT_NAME else "Sin Nombre",
                            'drive_link': row[self.COL_DRIVE_LINK - 1] if len(row) >= self.COL_DRIVE_LINK else "",
                            'dropbox_link': row[self.COL_DBX_LINK - 1] if len(row) >= self.COL_DBX_LINK else "",
                            'comments': row[self.COL_COMMENTS - 1] if len(row) >= self.COL_COMMENTS else ""
                        }
                        rows_data.append(row_data)
            
            return rows_data

        except Exception as e:
            logger.error(f"Error leyendo filas pendientes: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def update_status(self, row_idx, status):
        """Actualiza la columna F (STATUS)."""
        try:
            self.sheet.update_cell(row_idx, self.COL_STATUS, status)
            logger.info(f"Fila {row_idx} -> Status actualizado a: {status}")
        except Exception as e:
            logger.error(f"Error actualizando status en fila {row_idx}: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def write_output_link(self, row_idx, link):
        """Escribe el link del Google Doc generado en la columna G."""
        try:
            self.sheet.update_cell(row_idx, self.COL_OUTPUT_LINK, link)
            logger.info(f"Fila {row_idx} -> Link guardado exitosamente.")
        except Exception as e:
            logger.error(f"Error escribiendo link en fila {row_idx}: {e}")
            raise

# Instancia global para usar en otros archivos
sheets_service = SheetsService()