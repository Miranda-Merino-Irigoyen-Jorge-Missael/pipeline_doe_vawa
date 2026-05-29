import os
import json
import logging
import PyPDF2
from src.services.sheets_service import sheets_service
from src.services.drive_service import drive_service
from src.services.dropbox_service import dropbox_service
from src.core.vertex_claude import vertex_claude
from src.workflows.fase2_process import fase2_workflow

# IMPORTANTE: Aquí importaremos el nuevo constructor de plantillas que haremos en el Paso 3
from src.services.template_builder import template_builder 
from src.core.google_client import google_manager

logger = logging.getLogger(__name__)

class Fase1Workflow:
    def __init__(self):
        # Cambiamos la instrucción para obligar a Claude a devolver JSON puro
        self.system_instruction = (
            "Eres un asistente legal experto en la revisión de casos VAWA. "
            "Tu tarea es analizar meticulosamente las transcripciones y evidencias. "
            "DEBES DEVOLVER TU RESPUESTA ESTRICTAMENTE EN FORMATO JSON VÁLIDO. "
            "No incluyas explicaciones, introducciones, ni bloques de markdown (no uses ```json). Solo el JSON puro."
        )
        # El ID de tu plantilla base de Google Docs (con los 2 tabs)
        self.TEMPLATE_ID = "1Mxxs5FHI4XFTVvnXPeLDLVocRnJnTADWsmlZPJ0pQVE"

    def extract_text_from_file(self, file_path: str) -> str:
        text = ""
        try:
            if file_path.endswith('.txt'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            elif file_path.endswith('.pdf'):
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
        except Exception as e:
            logger.error(f"Error extrayendo texto del archivo {file_path}: {e}")
        return text

    def run(self):
        logger.info(">>> INICIANDO FLUJO DE FASE 1 Y 2 (ARQUITECTURA JSON PURA) <<<")
        pending_rows = sheets_service.get_pending_rows()
        
        if not pending_rows:
            logger.info("No hay casos en estado 'PENDING PROCESS'.")
            return

        for row in pending_rows:
            self._process_single_row(row)
            
        logger.info(">>> FLUJO PIPELINE FINALIZADO <<<")

    def _process_single_row(self, row_data):
        row_idx = row_data['row_idx']
        client_name = row_data['client_name']
        relationship = row_data['relationship']
        dcl_link = row_data['dcl_link']
        dbx_folder = row_data['dropbox_folder_link']
        drive_trans = row_data['drive_transcripts_link']
        comments = row_data['comments']
        
        logger.info(f"--- Procesando fila {row_idx} | Cliente: {client_name} ---")

        try:
            sheets_service.update_status(row_idx, "PROCESS (FASE 1 & 2)")
            
            # --- 1. DESCARGA Y CONVERSIÓN DE DOCUMENTOS ---
            file_paths = []
            temp_dir = os.path.join("temp", f"caso_{row_idx}")
            os.makedirs(temp_dir, exist_ok=True)

            if dcl_link:
                local_dcl = dropbox_service.download_from_shared_link(dcl_link, os.path.join(temp_dir, "dcl_original.docx"))
                if local_dcl:
                    pdf_dcl = drive_service.convert_local_docx_to_pdf(local_dcl, os.path.join(temp_dir, "dcl_convertido.pdf"))
                    if pdf_dcl: file_paths.append(pdf_dcl)

            if dbx_folder:
                if "drive.google.com" in dbx_folder or "docs.google.com" in dbx_folder:
                    folder_files = drive_service.download_folder_contents(dbx_folder, os.path.join(temp_dir, "evidencias"))
                else:
                    folder_files = dropbox_service.download_folder_contents(dbx_folder, os.path.join(temp_dir, "evidencias"))
                
                for f_path in folder_files:
                    if f_path.endswith('.docx'):
                        pdf_ev = drive_service.convert_local_docx_to_pdf(f_path, f_path.replace('.docx', '.pdf'))
                        if pdf_ev: file_paths.append(pdf_ev)
                    elif f_path.endswith('.pdf') or f_path.endswith('.txt'):
                        file_paths.append(f_path)

            if drive_trans:
                trans_path = os.path.join(temp_dir, "transcripcion") 
                file_trans = drive_service.download_drive_link_as_pdf(drive_trans, trans_path)
                if file_trans: file_paths.append(file_trans)

            # --- 2. EXTRACCIÓN DE TEXTO ---
            documentos_texto = ""
            for f_path in file_paths:
                nombre_archivo = os.path.basename(f_path)
                texto_extraido = self.extract_text_from_file(f_path)
                if not texto_extraido.strip():
                    texto_extraido = "[El sistema intentó leer este archivo pero se extrajo texto vacío.]"
                documentos_texto += f"\n\n--- DOCUMENTO: {nombre_archivo} ---\n{texto_extraido}\n"

            # --- 3. CONSTRUCCIÓN DE INSTRUCCIONES FASE 1 (NUEVO FORMATO JSON) ---
            prompt_instructions = f"""
Tipo de relación con el perpetrador: {relationship}.
COMENTARIO PARTICULAR: {comments if comments else 'Ninguno.'}

--- INSTRUCCIONES PRINCIPALES ---
Usando los documentos, extrae información sobre TODOS los abusos que ha sufrido el cliente.
Debes devolver un ARREGLO JSON donde cada objeto represente un abuso.

Estructura requerida:
[
  {{
    "fragmento": "Cita o resumen del testimonio",
    "evento": "Descripción muy breve del evento o patrón (Evento) / (Patrón)",
    "clasificacion": "Tipo de abuso",
    "pagina": "Nombre del documento y página"
  }}
]

¡REGLA DE ORO!: OBLIGATORIAMENTE debes buscar y extraer eventos de abuso de TODOS Y CADA UNO de los documentos proporcionados.
NO devuelvas nada más que el arreglo de objetos JSON.
"""

            # --- 4. LLAMAR A CLAUDE (FASE 1) CON CACHÉ ---
            logger.info("Enviando prompt Fase 1 a Claude (Creando caché / Solicitando JSON)...")
            json_response = vertex_claude.generate_response_with_cache(
                system_instruction=self.system_instruction,
                cached_documents_text=documentos_texto,
                prompt_instructions=prompt_instructions
            )

            # Limpiamos y convertimos a diccionario de Python
            clean_json = json_response.replace("```json", "").replace("```", "").strip()
            abusos_data = json.loads(clean_json)
            logger.info(f"[✓] Se extrajeron {len(abusos_data)} abusos en formato JSON estructurado.")

            # --- 5. COPIAR LA PLANTILLA (DRIVE) ---
            doc_title = f"Analisis_VAWA_{client_name.replace(' ', '_')}"
            document_id, doc_link = drive_service.copy_template(self.TEMPLATE_ID, doc_title)

            # --- 6. INYECTAR TABLA EN PESTAÑA 1 ---
            # Obtenemos el ID de la primera pestaña (Fase 1) usando el índice 0
            tab1_id = google_manager.get_tab_id_by_index(document_id, tab_index=0)
            template_builder.inject_fase1_table(document_id, tab1_id, abusos_data)

            # --- 7. EJECUTAR FASE 2 ---
            logger.info(">>> Detonando Fase 2 automáticamente <<<")
            fase2_exitosa = fase2_workflow.run_fase_2(
                document_id=document_id, 
                client_name=client_name, 
                documentos_texto=documentos_texto
            )

            # --- 8. GUARDAR Y COMPLETAR EN SHEETS ---
            if fase2_exitosa:
                sheets_service.write_output_link(row_idx, doc_link)
                sheets_service.update_status(row_idx, "FASE 1 Y 2 COMPLETED")
                logger.info(f"--- Fila {row_idx} completada con éxito (Ambas Fases) ---")
            else:
                sheets_service.write_output_link(row_idx, doc_link)
                sheets_service.update_status(row_idx, "FASE 1 OK - ERROR FASE 2")
                logger.warning(f"--- Fila {row_idx} completada parcialmente (Falló Fase 2) ---")

        except Exception as e:
            logger.error(f"Error procesando el cliente {client_name}: {e}")
            try:
                sheets_service.update_status(row_idx, "ERROR EN PIPELINE")
            except:
                pass

fase1_workflow = Fase1Workflow()