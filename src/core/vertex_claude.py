import base64
import logging
from anthropic import AnthropicVertex
from src.config import Config
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class VertexClaudeClient:
    """
    Cliente para comunicarse con Claude a través de Google Vertex AI,
    implementando Prompt Caching y Streaming para operaciones masivas.
    """
    def __init__(self):
        self.project_id = Config.PROJECT_ID
        self.location = Config.LOCATION
        self.model = "claude-sonnet-4-6" 
        
        try:
            # Nos conectamos a Vertex AI directamente como lo requiere la arquitectura
            self.client = AnthropicVertex(
                project_id=self.project_id,
                region=self.location,
            )
            logger.info(f"Cliente AnthropicVertex inicializado en {self.location}")
        except Exception as e:
            logger.error(f"Error inicializando AnthropicVertex: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_exponential(multiplier=1, min=4, max=15)
    )
    def generate_response_with_cache(self, system_instruction, cached_documents_text, prompt_instructions, pdf_documents=None):
        """
        Envía un prompt utilizando block-level caching y streaming de texto.
        pdf_documents: lista de dicts {"name": str, "data": bytes} para PDFs escaneados.
        """
        try:
            logger.info(f"Enviando petición a {self.model} con Prompt Caching y Streaming (Max 60k)...")

            content_blocks = []

            # Bloques PDF nativos (para documentos escaneados / imágenes)
            if pdf_documents:
                for pdf in pdf_documents:
                    b64_data = base64.standard_b64encode(pdf["data"]).decode("utf-8")
                    content_blocks.append({
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": b64_data
                        },
                        "title": pdf["name"],
                        "cache_control": {"type": "ephemeral"}
                    })
                logger.info(f"{len(pdf_documents)} PDF(s) adjuntados como bloques nativos.")

            # Bloque de texto (docx/txt ya extraídos)
            if cached_documents_text.strip():
                content_blocks.append({
                    "type": "text",
                    "text": f"--- DOCUMENTOS EXTRAÍDOS BASE ---\n{cached_documents_text}",
                    "cache_control": {"type": "ephemeral"}
                })

            # Instrucciones (sin caché — cambian por caso)
            content_blocks.append({
                "type": "text",
                "text": prompt_instructions
            })

            messages = [
                {
                    "role": "user",
                    "content": content_blocks
                }
            ]
            
            output_text = ""
            
            # Implementación del SDK de Anthropic para streaming explícito
            with self.client.messages.stream(
                model=self.model,
                max_tokens=60000, 
                system=system_instruction,
                messages=messages,
                temperature=0.5 
            ) as stream:
                for text in stream.text_stream:
                    output_text += text
            
            # Extraemos la metadata de uso del mensaje final unificado
            final_message = stream.get_final_message()
            usage = final_message.usage
            
            logger.info(f"Uso tokens - Input: {usage.input_tokens} | Output: {usage.output_tokens} | Cache Creation: {getattr(usage, 'cache_creation_input_tokens', 0)} | Cache Read: {getattr(usage, 'cache_read_input_tokens', 0)}")
            
            return output_text
            
        except Exception as e:
            logger.error(f"Error generando respuesta con Claude vía Vertex (Caché/Stream): {e}")
            raise

# Instancia global para importar en el flujo de trabajo
vertex_claude = VertexClaudeClient()