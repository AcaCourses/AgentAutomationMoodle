import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

class Config:
    MOODLE_BASE_URL: str = os.getenv("MOODLE_BASE_URL", "https://sea.acatlan.unam.mx").rstrip("/")
    MOODLE_USER: str = os.getenv("MOODLE_USER", "").strip().strip('"').strip("'")
    MOODLE_PASS: str = os.getenv("MOODLE_PASS", "").strip().strip('"').strip("'")
    
    # Puede ser un solo ID o varios separados por coma (ej. "22841,22842")
    RAW_COURSE_ID: str = os.getenv("MOODLE_COURSE_ID", "22841,22842")
    
    API_SECRET: str = os.getenv("API_SECRET", "mi_clave_secreta")
    GROQ_API_KEY_1: str = os.getenv("GROQ_API_KEY_1", "")
    GROQ_API_KEY_2: str = os.getenv("GROQ_API_KEY_2", "")
    NGROK_AUTHTOKEN: str = os.getenv("NGROK_AUTHTOKEN", "")
    
    SESSION_FILE: str = "session.json"
    JSON_DATA_FILE: str = "recursos.json"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    @property
    def GROQ_API_KEYS(self) -> List[str]:
        """Retorna una lista de API Keys de Groq para rotación/balanceo."""
        tokens = []
        if self.GROQ_API_KEY_1:
            tokens.append(self.GROQ_API_KEY_1.strip())
        if self.GROQ_API_KEY_2:
            tokens.append(self.GROQ_API_KEY_2.strip())
        
        # Eliminar duplicados manteniendo el orden
        seen = set()
        result = []
        for t in tokens:
            if t not in seen:
                seen.add(t)
                result.append(t)
        return result

    @property
    def COURSE_IDS(self) -> List[str]:
        """Retorna la lista de IDs de cursos configurados."""
        return [c.strip() for c in self.RAW_COURSE_ID.split(",") if c.strip()]

config = Config()
