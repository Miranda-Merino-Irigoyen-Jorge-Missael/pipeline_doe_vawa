import logging
from src.core.google_client import google_manager
from src.config import Config
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class SheetsService:
    """
    Servicio para leer y actualizar la hoja de control de la Fase 1.
    """
    
    # NUEVO MAPEO DE COLUMNAS (Índice base 1 para gspread)
    COL_CLIENT_NAME   = 1  # A: Nombre del cliente
    COL_RELATIONSHIP  = 2  # B: Tipo de relación (Hijo, Hija, Esposo, Esposa)
    COL_COLLABORATOR  = 3  # C: Colaborador
    COL_DCL_LINK      = 4  # D: Link DCL (Dropbox)
    COL_DBX_FOLDER    = 5  # E: Carpeta Dropbox (múltiples docs)
    COL_DRIVE_TRANS   = 6  # F: Transcripciones Drive
    COL_COMMENTS      = 7  # G: COMENTARIO PARA CLAUDE
    COL_COMPLEMENTO   = 8  # H: COMPLEMENTO (Google Doc / PDF / Word)
    COL_STATUS        = 9  # I: STATUS
    COL_OUTPUT_LINK   = 10 # J: Entregable (Doc)

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
        Busca todas las filas cuyo STATUS (Col H) sea 'PENDING PROCESS'.
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
                        # Extraemos la data con seguridad (usando dict.get o validando longitud)
                        def get_col_val(col_idx):
                            return row[col_idx - 1].strip() if len(row) >= col_idx else ""

                        row_data = {
                            'row_idx': row_idx,
                            'client_name': get_col_val(self.COL_CLIENT_NAME),
                            'relationship': get_col_val(self.COL_RELATIONSHIP),
                            'collaborator': get_col_val(self.COL_COLLABORATOR),
                            'dcl_link': get_col_val(self.COL_DCL_LINK),
                            'dropbox_folder_link': get_col_val(self.COL_DBX_FOLDER),
                            'drive_transcripts_link': get_col_val(self.COL_DRIVE_TRANS),
                            'comments': get_col_val(self.COL_COMMENTS),
                            'complemento_link': get_col_val(self.COL_COMPLEMENTO)
                        }
                        
                        # Validación básica de seguridad
                        if not row_data['client_name']:
                            row_data['client_name'] = "Sin Nombre"
                            
                        rows_data.append(row_data)
            
            return rows_data

        except Exception as e:
            logger.error(f"Error leyendo filas pendientes: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def update_status(self, row_idx, status):
        """Actualiza la columna I (STATUS)."""
        try:
            self.sheet.update_cell(row_idx, self.COL_STATUS, status)
            logger.info(f"Fila {row_idx} -> Status actualizado a: {status}")
        except Exception as e:
            logger.error(f"Error actualizando status en fila {row_idx}: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def write_output_link(self, row_idx, link):
        """Escribe el link del Google Doc generado en la columna J."""
        try:
            self.sheet.update_cell(row_idx, self.COL_OUTPUT_LINK, link)
            logger.info(f"Fila {row_idx} -> Link guardado exitosamente.")
        except Exception as e:
            logger.error(f"Error escribiendo link en fila {row_idx}: {e}")
            raise

# Instancia global para usar en otros archivos
sheets_service = SheetsService()