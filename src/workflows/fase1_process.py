import logging
from src.services.sheets_service import sheets_service
from src.services.drive_service import drive_service
from src.services.dropbox_service import dropbox_service
from src.core.vertex_claude import vertex_claude

logger = logging.getLogger(__name__)

class Fase1Workflow:
    """
    Orquestador principal de la Fase 1:
    1. Lee filas con 'PENDING PROCESS'.
    2. Cambia estado a 'PROCESS (FASE 1)'.
    3. Llama a Claude con un prompt inicial.
    4. Crea el Google Doc y guarda el link.
    """
    
    def __init__(self):
        # Instrucción base para Claude en esta fase inicial
        self.system_instruction = (
            "Eres un asistente legal experto. Tu tarea por ahora es procesar "
            "la información y crear un borrador inicial o esqueleto del documento DOE. "
            "Sigue estrictamente las instrucciones del colaborador."
        )

    def run(self):
        logger.info(">>> INICIANDO FLUJO DE FASE 1 <<<")
        
        # 1. Obtener filas pendientes
        pending_rows = sheets_service.get_pending_rows()
        
        if not pending_rows:
            logger.info("No hay casos en estado 'PENDING PROCESS'.")
            return

        logger.info(f"Se encontraron {len(pending_rows)} filas para procesar.")

        # 2. Procesar cada fila
        for row in pending_rows:
            self._process_single_row(row)
            
        logger.info(">>> FLUJO DE FASE 1 FINALIZADO <<<")

    def _process_single_row(self, row_data):
        row_idx = row_data['row_idx']
        client_name = row_data['client_name']
        dropbox_link = row_data['dropbox_link']
        comments = row_data['comments']
        
        logger.info(f"--- Procesando fila {row_idx} | Cliente: {client_name} ---")

        try:
            # A. Actualizar estado a PROCESS (FASE 1)
            sheets_service.update_status(row_idx, "PROCESS (FASE 1)")

            # B. Validar link de Dropbox (por ahora solo validamos, no descargamos)
            is_valid_dbx = dropbox_service.validate_link(dropbox_link)
            if not is_valid_dbx:
                logger.warning(f"El link de Dropbox de {client_name} parece inválido, pero continuaremos.")

            # C. Construir el prompt para Claude
            prompt = (
                f"Por favor genera un documento inicial de análisis para el cliente: {client_name}.\n\n"
                f"COMENTARIOS ESPECIALES DEL COLABORADOR:\n"
                f"{comments if comments else 'Ningún comentario adicional.'}\n\n"
                "Genera un documento estructurado en formato Markdown (con títulos, subtítulos y viñetas) "
                "que demuestre que has recibido esta información. Inventa un poco de texto de relleno profesional "
                "solo para probar la estructura."
            )

            # D. Llamar a Claude vía Vertex AI
            response_text = vertex_claude.generate_response(
                prompt=prompt, 
                system_instruction=self.system_instruction
            )

            # E. Crear el Google Doc en la carpeta destino
            doc_title = f"DOE_Fase1_{client_name.replace(' ', '_')}"
            doc_link = drive_service.create_google_doc(title=doc_title, content=response_text)

            # F. Escribir el link en la Columna G
            sheets_service.write_output_link(row_idx, doc_link)

            # G. Marcar como completado
            sheets_service.update_status(row_idx, "FASE 1 COMPLETED")

        except Exception as e:
            logger.error(f"Error procesando el cliente {client_name}: {e}")
            # Si falla, lo marcamos en la hoja para que el equipo lo sepa
            try:
                sheets_service.update_status(row_idx, "ERROR EN FASE 1")
            except:
                pass

# Instancia del workflow
fase1_workflow = Fase1Workflow()