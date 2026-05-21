import logging
from anthropic import AnthropicVertex
from src.config import Config
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class VertexClaudeClient:
    """
    Cliente para comunicarse con Claude 3.5 Sonnet a través de Google Vertex AI.
    """
    def __init__(self):
        self.project_id = Config.PROJECT_ID
        self.location = Config.LOCATION
        
        # El nombre oficial del modelo en Vertex AI para Claude 3.5 Sonnet
        self.model = "claude-sonnet-4-6" 
        
        try:
            # AnthropicVertex detectará automáticamente las credenciales de GCP 
            # (Ej. las generadas por 'gcloud auth application-default login')
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
    def generate_response(self, prompt, system_instruction=""):
        """
        Envía un prompt a Claude y devuelve el texto de respuesta.
        """
        try:
            logger.info(f"Enviando petición a {self.model}...")
            
            # Formateamos el mensaje según la estructura requerida por Anthropic
            messages = [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8192, # Claude 3.5 Sonnet soporta hasta 8192 tokens de salida
                system=system_instruction, # Las instrucciones de "quién es" van aquí
                messages=messages,
                temperature=0.2 # Temperatura baja para mantener un tono formal/preciso
            )
            
            # Extraemos y retornamos únicamente el texto generado
            output_text = response.content[0].text
            logger.info("Respuesta de Claude recibida con éxito.")
            return output_text
            
        except Exception as e:
            logger.error(f"Error generando respuesta con Claude vía Vertex: {e}")
            raise

# Instancia global para importar en el flujo de trabajo
vertex_claude = VertexClaudeClient()