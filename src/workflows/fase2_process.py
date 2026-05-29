import json
import logging
from src.core.vertex_claude import vertex_claude
from src.services.template_builder import template_builder

logger = logging.getLogger(__name__)

class Fase2Workflow:
    def __init__(self):
        self.system_instruction = (
            "Eres un asistente legal experto. Tu única tarea es extraer información "
            "de los documentos proporcionados y devolverla ESTRICTAMENTE en formato JSON "
            "válido. No incluyas explicaciones, introducciones ni markdown (no uses ```json), solo el JSON puro."
        )

    def build_json_prompt(self, client_name):
        return f"""
Analiza los documentos del cliente: {client_name}.
Extrae la siguiente información para llenar un formulario legal interno (Template 3.2). 
Si un dato no aplica o no se encuentra en los documentos, coloca "N/A".

INSTRUCCIÓN ESPECIAL PARA 'conductas_abusivas_dcl': Para este campo, debes leer ÚNICAMENTE el documento de la DCL. Redacta las conductas en tiempo pretérito perfecto compuesto (ej. 'Abuser ha golpeado...').

Devuelve un JSON estrictamente con esta estructura y llaves exactas:
{{
    "cl_nombre": "",
    "abuser_nombre": "",
    "cl_dob": "",
    "abuser_dob": "",
    "cl_pob": "",
    "abuser_pob": "",
    "cl_altura": "",
    "abuser_altura": "",
    "cl_peso": "",
    "abuser_peso": "",
    "estado_civil": "",
    "estatus_legal": "",
    "cl_cargos": "",
    "abuser_cargos": "",
    "hijos_comun": "",
    "viven_juntos": "",
    "conductas_abusivas_dcl": "",
    "evidencia_fisico": "",
    "ausencia_fisico": "",
    "evidencia_psico": "",
    "ausencia_psico": "",
    "evidencia_financiero": "",
    "ausencia_financiero": "",
    "evidencia_legal": "",
    "ausencia_legal": "",
    "uscis_aislamiento_ej": "",
    "uscis_aislamiento_cons": "",
    "uscis_humillacion_ej": "",
    "uscis_humillacion_cons": "",
    "uscis_degradacion_ej": "",
    "uscis_degradacion_cons": "",
    "uscis_economico_ej": "",
    "uscis_economico_cons": "",
    "uscis_coercion_ej": "",
    "uscis_coercion_cons": "",
    "uscis_amenazas_ej": "",
    "uscis_amenazas_cons": "",
    "uscis_miedo_ej": "",
    "uscis_miedo_cons": "",
    "uscis_control_ej": "",
    "uscis_control_cons": "",
    "uscis_negacion_ej": "",
    "uscis_negacion_cons": "",
    "uscis_deportacion_ej": "",
    "uscis_deportacion_cons": "",
    "uscis_hijos_ej": "",
    "uscis_hijos_cons": "",
    "uscis_detencion_ej": "",
    "uscis_detencion_cons": "",
    "uscis_psicosexual_ej": "",
    "uscis_psicosexual_cons": "",
    "uscis_patron_ej": "",
    "uscis_patron_cons": "",
    "uscis_terceros_ej": "",
    "uscis_terceros_cons": "",
    "uscis_testigo_hijo_ej": "",
    "uscis_testigo_hijo_cons": "",
    "tabla_impactos": [
        {{
            "ano": "",
            "accion": "",
            "afecta": "",
            "impacto": ""
        }}
    ],
    "tabla_financieros": [
        {{
            "descripcion": "",
            "fecha": "",
            "monto": "",
            "consecuencia": ""
        }}
    ]
}}
"""

    def run_fase_2(self, document_id, client_name, documentos_texto):
        try:
            logger.info(f"--- Iniciando Fase 2 (Template 3.2) para el cliente {client_name} ---")
            
            prompt_instructions = self.build_json_prompt(client_name)
            
            logger.info("Solicitando extracción masiva JSON (Esperando Cache Hit)...")
            response_text = vertex_claude.generate_response_with_cache(
                system_instruction=self.system_instruction,
                cached_documents_text=documentos_texto, 
                prompt_instructions=prompt_instructions
            )
            
            clean_json = response_text.replace("```json", "").replace("```", "").strip()
            extracted_data = json.loads(clean_json)
            logger.info("[✓] JSON de Template 3.2 extraído y parseado correctamente.")
            
            # Usamos el nuevo método de reemplazo masivo que programamos en el Paso 3
            template_builder.fill_fase2_template(document_id, extracted_data)
            
            logger.info(f"--- Fase 2 completada exitosamente para {client_name} ---")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parseando el JSON de Claude: {e}\nRespuesta cruda: {response_text}")
            return False
        except Exception as e:
            logger.error(f"Error general en Fase 2: {e}")
            return False

fase2_workflow = Fase2Workflow()