import os
import logging
import PyPDF2
from src.services.sheets_service import sheets_service
from src.services.drive_service import drive_service
from src.services.dropbox_service import dropbox_service
from src.core.vertex_claude import vertex_claude

logger = logging.getLogger(__name__)

class Fase1Workflow:
    """
    Orquestador principal de la Fase 1.
    """
    
    def __init__(self):
        self.system_instruction = (
            "Eres un asistente legal experto en la revisión de casos VAWA. "
            "Tu tarea es analizar meticulosamente las transcripciones y evidencias, "
            "y extraer los hechos tal como se solicitan. Actúa con extrema precisión."
        )

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extrae el texto de un archivo PDF usando PyPDF2."""
        text = ""
        try:
            with open(pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            logger.error(f"Error extrayendo texto del PDF {pdf_path}: {e}")
        return text

    def run(self):
        logger.info(">>> INICIANDO FLUJO DE FASE 1 <<<")
        pending_rows = sheets_service.get_pending_rows()
        
        if not pending_rows:
            logger.info("No hay casos en estado 'PENDING PROCESS'.")
            return

        for row in pending_rows:
            self._process_single_row(row)
            
        logger.info(">>> FLUJO DE FASE 1 FINALIZADO <<<")

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
            sheets_service.update_status(row_idx, "PROCESS (FASE 1)")
            
            # --- 1. DESCARGA Y CONVERSIÓN DE DOCUMENTOS ---
            pdf_paths = []
            temp_dir = os.path.join("temp", f"caso_{row_idx}")
            os.makedirs(temp_dir, exist_ok=True)

            # A. Descargar DCL (Dropbox)
            if dcl_link:
                local_dcl = dropbox_service.download_from_shared_link(dcl_link, os.path.join(temp_dir, "dcl_original.docx"))
                if local_dcl:
                    pdf_dcl = drive_service.convert_local_docx_to_pdf(local_dcl, os.path.join(temp_dir, "dcl_convertido.pdf"))
                    if pdf_dcl: pdf_paths.append(pdf_dcl)

            # B. Descargar Carpeta Dropbox (Evidencias)
            if dbx_folder:
                folder_files = dropbox_service.download_folder_contents(dbx_folder, os.path.join(temp_dir, "evidencias"))
                for i, f_path in enumerate(folder_files):
                    if f_path.endswith('.docx'):
                        pdf_ev = drive_service.convert_local_docx_to_pdf(f_path, f_path.replace('.docx', '.pdf'))
                        if pdf_ev: pdf_paths.append(pdf_ev)
                    elif f_path.endswith('.pdf'):
                        pdf_paths.append(f_path)

            # C. Descargar Transcripciones (Drive)
            if drive_trans:
                pdf_trans = drive_service.download_drive_link_as_pdf(drive_trans, os.path.join(temp_dir, "transcripcion.pdf"))
                if pdf_trans: pdf_paths.append(pdf_trans)

            # --- 2. EXTRACCIÓN DE TEXTO ---
            documentos_texto = ""
            for idx, pdf in enumerate(pdf_paths):
                logger.info(f"Extrayendo texto de: {os.path.basename(pdf)}")
                texto_extraido = self.extract_text_from_pdf(pdf)
                documentos_texto += f"\n\n--- DOCUMENTO {idx + 1} ---\n{texto_extraido}\n"

            # --- 3. CONSTRUCCIÓN DEL SÚPER PROMPT ---
            prompt = f"""
Analiza los siguientes documentos relacionados con el cliente: {client_name}.
Tipo de relación con el perpetrador: {relationship}.

COMENTARIO PARTICULAR: 
{comments if comments else 'Ninguno.'}

DOCUMENTOS EXTRAÍDOS:
{documentos_texto}

--- INSTRUCCIONES PRINCIPALES ---
Usando lo anterior, necesito que realices una tabla donde se contenga información sobre TODOS los abusos que ha sufrido el cliente relacionados con el caso.
La tabla deberá de contener las siguientes columnas:

- Fragmento del Testimonio
- Evento / Patrón
- Clasificación del Abuso
- Página

Cabe aclarar que en la columna 'Evento / Patrón' debe de colocarse de qué va el evento de forma muy breve y cuando se termine eso debe de ponerse al final entre paréntesis si es un Evento o si es un Patrón.

EJEMPLO:
- Agresión física directa resultando en una lesión cutánea y hematoma en el rostro. (Evento)
- Sustracción sistemática de dinero en efectivo de las pertenencias personales para financiar adicciones. (Patrón)

Recuerda que esto anterior solo es un ejemplo, tú solo te basarás en los documentos proporcionados.
No inicies con ningún tipo de introducción o presentación, limítate a redactar la tabla directamente.

--- INSTRUCCIONES DE FORMATO ESTÉTICO (MUY IMPORTANTE) ---
Genera tu respuesta ÚNICAMENTE en código HTML válido, sin markdown (sin ```html). 
Utiliza estilos CSS integrados para que la tabla se vea estética al convertirse en Google Doc:
- La etiqueta <table> debe tener style="width: 100%; border-collapse: collapse; font-family: Arial, sans-serif;"
- La etiqueta <th> debe tener style="background-color: #4a86e8; color: white; padding: 10px; border: 1px solid #cccccc; text-align: left;"
- La etiqueta <td> debe tener style="padding: 10px; border: 1px solid #cccccc; vertical-align: top;"
- Aplica un fondo gris muy claro (background-color: #f9f9f9;) a las filas pares (<tr>).
"""

            # --- 4. LLAMAR A CLAUDE ---
            logger.info("Enviando súper prompt a Claude...")
            html_response = vertex_claude.generate_response(
                prompt=prompt, 
                system_instruction=self.system_instruction
            )

            # Limpiar posible markdown residual si Claude lo agrega por error
            html_response = html_response.replace("```html", "").replace("```", "").strip()

            # --- 5. CREAR GOOGLE DOC ---
            doc_title = f"Analisis_VAWA_{client_name.replace(' ', '_')}"
            # Pasamos as_html=True para que aplique los estilos de la tabla
            doc_link = drive_service.create_google_doc(title=doc_title, content=html_response, as_html=True)

            # --- 6. GUARDAR Y COMPLETAR ---
            sheets_service.write_output_link(row_idx, doc_link)
            sheets_service.update_status(row_idx, "FASE 1 COMPLETED")
            
            logger.info(f"--- Fila {row_idx} completada con éxito ---")

        except Exception as e:
            logger.error(f"Error procesando el cliente {client_name}: {e}")
            try:
                sheets_service.update_status(row_idx, "ERROR EN FASE 1")
            except:
                pass

# Instancia del workflow
fase1_workflow = Fase1Workflow()