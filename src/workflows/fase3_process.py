import json
import logging
from src.config import Config
from src.core.vertex_claude import vertex_claude
from src.services.template_builder import template_builder

logger = logging.getLogger(__name__)

class Fase3Workflow:
    def __init__(self):
        # Cargamos el prompt de la Fase 3 desde el archivo de texto
        try:
            with open(Config.PROMPT_FASE_3_PATH, 'r', encoding='utf-8') as file:
                self.system_instruction = file.read()
        except Exception as e:
            logger.error(f"Error al leer el prompt de la Fase 3: {e}")
            self.system_instruction = "Eres un Abogado Estadounidense experto..." # Fallback de seguridad

    def build_json_prompt(self, client_name, comments):
        return f"""
Vas a redactar el DOE completo para el cliente: {client_name}.
COMENTARIO PARTICULAR DEL CASO (instrucciones extra): {comments if comments else 'Ninguno.'}

INSTRUCCIÓN CRÍTICA DE EXTENSIÓN Y EXHAUSTIVIDAD:
Los documentos fuente contienen decenas de miles de tokens de información. Tu output DEBE reflejar eso.
Para CADA evento, sigue este proceso OBLIGATORIO antes de escribir:
1. ESCANEA todos los documentos y extrae CADA fragmento de información relacionado con ese evento (fechas, lugares, palabras exactas, consecuencias físicas, consecuencias emocionales, contexto previo, qué pasó después, cómo afectó la relación, cuánto tiempo duró el patrón, testigos, costos económicos, todo).
2. LUEGO escribe el contenido_narrativo expandiendo CADA uno de esos fragmentos en prosa fluida. Ningún detalle debe quedar fuera.
3. NO pares de escribir un evento hasta haber agotado TODO lo que los documentos dicen sobre ese incidente o patrón.

El campo 'contenido_narrativo' de cada evento rico en información DEBE tener mínimo 5 párrafos sustanciales. Un evento con mucha información puede tener 8, 10 o más párrafos — eso es correcto y esperado. Es MEJOR pecar de extenso que de breve.

NO termines el JSON hasta estar seguro de que TODA la información relevante de los documentos fue incorporada en algún evento.

¡REGLA CRÍTICA DE FORMATO JSON! (ANTI-ERRORES):
1. ESTÁ ESTRICTAMENTE PROHIBIDO usar comillas dobles (" ") dentro de tus textos. 
2. Si necesitas hacer una cita de diálogo, usa EXCLUSIVAMENTE comillas simples (' '). Ejemplo correcto: **_'Me costó con cremita'_**
3. Si usas saltos de línea dentro del texto, asegúrate de escaparlos correctamente con \\n.
4. Tu respuesta debe ser un JSON puro, válido y cerrado correctamente.

Genera los eventos siguiendo estrictamente las instrucciones de tu rol y retorna ÚNICA Y EXCLUSIVAMENTE el JSON solicitado.
"""

    def run_fase_3(self, document_id, tab_id, client_name, documentos_texto, comments, pdf_documents=None):
        try:
            logger.info(f"--- Iniciando Fase 3 (DOE - Eventos VAWA) para el cliente {client_name} ---")
            
            prompt_instructions = self.build_json_prompt(client_name, comments)
            
            # Aprovechamos el método con caché para ahorrar tokens
            logger.info("Solicitando extracción de Eventos VAWA (Esperando Cache Hit)...")
            response_text = vertex_claude.generate_response_with_cache(
                system_instruction=self.system_instruction,
                cached_documents_text=documentos_texto, 
                prompt_instructions=prompt_instructions,
                pdf_documents=pdf_documents
            )
            
            clean_json = response_text.replace("```json", "").replace("```", "").strip()
            extracted_data = json.loads(clean_json)
            logger.info("[OK] JSON de Fase 3 (Eventos VAWA) extraído y parseado correctamente.")
            
            # Inyectamos en la tercera pestaña usando el método que creamos hace un momento
            template_builder.inject_fase3_events(document_id, tab_id, extracted_data)
            
            logger.info(f"--- Fase 3 completada exitosamente para {client_name} ---")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parseando el JSON de Claude en Fase 3: {e}\nRespuesta cruda: {response_text}")
            return False
        except Exception as e:
            logger.error(f"Error general en Fase 3: {e}")
            return False

fase3_workflow = Fase3Workflow()