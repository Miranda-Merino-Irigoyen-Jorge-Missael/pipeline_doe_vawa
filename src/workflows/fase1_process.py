import os
import json
import logging
import PyPDF2
from docx import Document as DocxDocument
from src.services.sheets_service import sheets_service
from src.services.drive_service import drive_service
from src.services.dropbox_service import dropbox_service
from src.core.vertex_claude import vertex_claude

from src.workflows.fase2_process import fase2_workflow
from src.workflows.fase3_process import fase3_workflow  # IMPORTACIÓN DE FASE 3

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
        # El ID de tu plantilla base de Google Docs (Asegúrate de que esta plantilla ya tenga 3 Tabs)
        self.TEMPLATE_ID = "1Mxxs5FHI4XFTVvnXPeLDLVocRnJnTADWsmlZPJ0pQVE"

    def extract_text_from_file(self, file_path: str) -> str:
        text = ""
        try:
            if file_path.endswith('.txt'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            elif file_path.endswith('.docx'):
                doc = DocxDocument(file_path)
                text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            elif file_path.endswith('.pdf'):
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
        except Exception as e:
            logger.error(f"Error extrayendo texto del archivo {file_path}: {e}")
        if not text.strip():
            logger.warning(f"[AVISO] Texto vacío extraído de: {os.path.basename(file_path)}")
        else:
            logger.info(f"Texto extraído de {os.path.basename(file_path)}: {len(text)} caracteres")
        return text

    def run(self):
        logger.info(">>> INICIANDO FLUJO DE FASE 1, 2 Y 3 (ARQUITECTURA JSON PURA) <<<")
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
        complemento_link = row_data.get('complemento_link', '')
        
        logger.info(f"--- Procesando fila {row_idx} | Cliente: {client_name} ---")

        try:
            sheets_service.update_status(row_idx, "PROCESS (FASES 1,2,3)")
            
            # --- 1. DESCARGA Y CONVERSIÓN DE DOCUMENTOS ---
            file_paths = []
            temp_dir = os.path.join("temp", f"caso_{row_idx}")
            os.makedirs(temp_dir, exist_ok=True)

            if dcl_link:
                # Detectar si el link apunta a un PDF o DOCX según la URL
                dcl_url_lower = dcl_link.lower().split('?')[0]
                dcl_ext = ".pdf" if dcl_url_lower.endswith('.pdf') else ".docx"
                local_dcl = dropbox_service.download_from_shared_link(dcl_link, os.path.join(temp_dir, f"dcl_original{dcl_ext}"))
                if local_dcl:
                    if dcl_ext == ".docx":
                        pdf_dcl = drive_service.convert_local_docx_to_pdf(local_dcl, os.path.join(temp_dir, "dcl_convertido.pdf"))
                        if pdf_dcl: file_paths.append(pdf_dcl)
                    else:
                        file_paths.append(local_dcl)

            if dbx_folder:
                if "drive.google.com" in dbx_folder or "docs.google.com" in dbx_folder:
                    folder_files = drive_service.download_folder_contents(dbx_folder, os.path.join(temp_dir, "evidencias"))
                else:
                    folder_files = dropbox_service.download_folder_contents(dbx_folder, os.path.join(temp_dir, "evidencias"))
                
                for f_path in folder_files:
                    if f_path and (f_path.endswith('.docx') or f_path.endswith('.pdf') or f_path.endswith('.txt')):
                        file_paths.append(f_path)

            if drive_trans:
                trans_path = os.path.join(temp_dir, "transcripcion") 
                file_trans = drive_service.download_drive_link_as_pdf(drive_trans, trans_path)
                if file_trans: file_paths.append(file_trans)

            if complemento_link:
                logger.info("Descargando documento COMPLEMENTO...")
                if "dropbox.com" in complemento_link:
                    comp_url_lower = complemento_link.lower().split('?')[0]
                    comp_ext = ".pdf" if comp_url_lower.endswith('.pdf') else ".docx"
                    complemento_path = os.path.join(temp_dir, f"complemento{comp_ext}")
                    file_complemento = dropbox_service.download_from_shared_link(complemento_link, complemento_path)
                else:
                    complemento_path = os.path.join(temp_dir, "complemento")
                    file_complemento = drive_service.download_drive_link_as_pdf(complemento_link, complemento_path)
                if file_complemento:
                    file_paths.append(file_complemento)
                    logger.info(f"[OK] Complemento descargado: {os.path.basename(file_complemento)}")
                else:
                    logger.warning("No se pudo descargar el documento COMPLEMENTO. Se continúa sin él.")

            # --- 2. SEPARAR PDFs DE ARCHIVOS DE TEXTO ---
            pdf_documents = []   # Para enviar nativamente a Claude
            text_paths   = []    # Para extraer texto (docx / txt)

            for f_path in file_paths:
                if f_path and f_path.endswith('.pdf'):
                    try:
                        with open(f_path, 'rb') as fbin:
                            pdf_documents.append({"name": os.path.basename(f_path), "data": fbin.read()})
                        logger.info(f"PDF nativo: {os.path.basename(f_path)} ({os.path.getsize(f_path)//1024} KB)")
                    except Exception as e:
                        logger.warning(f"No se pudo leer el PDF {f_path}: {e}")
                elif f_path:
                    text_paths.append(f_path)

            # --- 3. EXTRACCIÓN DE TEXTO (solo docx / txt) ---
            documentos_texto = ""
            for f_path in text_paths:
                nombre_archivo = os.path.basename(f_path)
                texto_extraido = self.extract_text_from_file(f_path)
                if not texto_extraido.strip():
                    texto_extraido = "[El sistema intentó leer este archivo pero se extrajo texto vacío.]"
                documentos_texto += f"\n\n--- DOCUMENTO: {nombre_archivo} ---\n{texto_extraido}\n"

            logger.info(f"PDFs nativos: {len(pdf_documents)} | Archivos texto: {len(text_paths)} | Chars texto: {len(documentos_texto)}")

# --- 3. CONSTRUCCIÓN DE INSTRUCCIONES FASE 1 (NUEVO FORMATO JSON) ---
            regla_orden = ""
            relacion_limpia = str(relationship).strip().lower()
            if relacion_limpia in ['hijo', 'hija']:
                regla_orden = (
                    "REGLA ESPECIAL DE EDAD Y CRONOLOGÍA:\n"
                    "1. EDAD: Como la relación es 'Hija' o 'Hijo', debes prestar especial atención a la edad del perpetrador.\n"
                    "2. ORDEN CRONOLÓGICO: El arreglo JSON DEBE estar ordenado cronológicamente (desde que el abuser era más joven hasta lo más reciente). "
                    "Para los eventos donde no se mencione la edad explícita, debes analizar el contexto de la historia e INFERIR lógicamente en qué momento ocurrieron "
                    "para insertarlos en la posición correcta."
                )
            else:
                regla_orden = "REGLA DE ORDEN: El arreglo JSON DEBE estar ordenado cronológicamente, desde los eventos más antiguos hasta los más recientes."

            prompt_instructions = f"""
Tipo de relación con el perpetrador: {relationship}.
COMENTARIO PARTICULAR: {comments if comments else 'Ninguno.'}

{regla_orden}

--- INSTRUCCIONES PRINCIPALES ---
Usando los documentos, extrae información sobre TODOS los abusos que ha sufrido el cliente.
REQUISITO USCIS: Los abusos a extraer deben ser aquellos que califican bajo los estándares de USCIS para VAWA (abuso físico, crueldad mental extrema, control coercitivo, abuso psicológico o económico).

Debes devolver un ARREGLO JSON donde cada objeto represente un abuso.

Estructura requerida:
[
  {{
    "edad_abuser": "Edad del perpetrador al momento del evento (ej. '25 años', 'Infancia del cliente', 'No se menciona')",
    "descripcion": "Descripción CONCISA y directa del evento de abuso. Ve al grano, no incluyas citas exactas ni conteos innecesarios (ej. en vez de 'en al menos 2 ocasiones revisó su celular', pon solo 'revisaba su celular').",
    "consecuencias": "Consecuencias físicas, psicológicas, emocionales o económicas sufridas.",
    "continua_actualidad": "Si la conducta ya no ocurre, responde 'No'. Si no se menciona, 'No especificado'. Si la conducta continúa, responde 'Sí' seguido de una BREVE explicación (ej. 'Sí, actualmente le sigue enviando mensajes de acoso')."
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
                prompt_instructions=prompt_instructions,
                pdf_documents=pdf_documents if pdf_documents else None
            )

            clean_json = json_response.replace("```json", "").replace("```", "").strip()
            abusos_data = json.loads(clean_json)
            logger.info(f"[OK] Se extrajeron {len(abusos_data)} abusos en formato JSON estructurado.")

            # --- 5. COPIAR LA PLANTILLA (DRIVE) ---
            doc_title = f"Analisis_VAWA_{client_name.replace(' ', '_')}"
            document_id, doc_link = drive_service.copy_template(self.TEMPLATE_ID, doc_title)

            # --- 6. INYECTAR TABLA EN PESTAÑA 1 ---
            tab1_id = google_manager.get_tab_id_by_index(document_id, tab_index=0)
            template_builder.inject_fase1_table(document_id, tab1_id, abusos_data)

            # --- 7. EJECUTAR FASE 2 ---
            logger.info(">>> Detonando Fase 2 automáticamente <<<")
            fase2_exitosa = fase2_workflow.run_fase_2(
                document_id=document_id, 
                client_name=client_name, 
                documentos_texto=documentos_texto,
                pdf_documents=pdf_documents if pdf_documents else None
            )

            # --- 8. EJECUTAR FASE 3 (NUEVO) ---
            logger.info(">>> Detonando Fase 3 automáticamente (DOE - Eventos VAWA) <<<")
            tab3_id = google_manager.get_tab_id_by_index(document_id, tab_index=2)
            fase3_exitosa = False
            
            if tab3_id:
                fase3_exitosa = fase3_workflow.run_fase_3(
                    document_id=document_id,
                    tab_id=tab3_id,
                    client_name=client_name,
                    documentos_texto=documentos_texto,
                    comments=comments,
                    pdf_documents=pdf_documents if pdf_documents else None
                )
            else:
                logger.error("No se encontró la Pestaña 3 (índice 2) en el documento. Verifica tu plantilla base en Google Docs.")

            # --- 9. GUARDAR Y COMPLETAR EN SHEETS ---
            if fase2_exitosa and fase3_exitosa:
                sheets_service.write_output_link(row_idx, doc_link)
                sheets_service.update_status(row_idx, "FASES 1, 2 Y 3 COMPLETED")
                logger.info(f"--- Fila {row_idx} completada con éxito (Todas las fases) ---")
            else:
                sheets_service.write_output_link(row_idx, doc_link)
                sheets_service.update_status(row_idx, "PROCESADO CON ERRORES")
                logger.warning(f"--- Fila {row_idx} completada parcialmente (Ocurrió un error en Fase 2 o 3) ---")

        except Exception as e:
            logger.error(f"Error procesando el cliente {client_name}: {e}")
            try:
                sheets_service.update_status(row_idx, "ERROR EN PIPELINE")
            except:
                pass

fase1_workflow = Fase1Workflow()