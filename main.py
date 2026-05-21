import logging
import sys
from src.workflows.fase1_process import fase1_workflow

# Configuración de logs para ver todo claro en la terminal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("main")

def main():
    print("\n" + "="*50)
    print("🚀 PIPELINE DOE VAWA - MODO DESARROLLO (FASE 1)")
    print("="*50 + "\n")

    try:
        # Arranca el orquestador de la fase 1
        fase1_workflow.run()
        
    except KeyboardInterrupt:
        print("\n[!] Proceso detenido manualmente por el usuario (Ctrl+C).")
    except Exception as e:
        logger.error(f"ERROR FATAL NO CONTROLADO: {e}", exc_info=True)
    finally:
        print("\n" + "="*50)
        print("🛑 SISTEMA DETENIDO")
        print("="*50 + "\n")

if __name__ == "__main__":
    main()