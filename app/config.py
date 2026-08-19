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
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    HF_TOKEN: str = os.getenv("HF_TOKEN", "")
    NGROK_AUTHTOKEN: str = os.getenv("NGROK_AUTHTOKEN", "")
    
    SESSION_FILE: str = "session.json"
    JSON_DATA_FILE: str = "recursos.json"
    HF_MODEL: str = "Qwen/Qwen2.5-72B-Instruct"

    @property
    def COURSE_IDS(self) -> List[str]:
        """Retorna la lista de IDs de cursos configurados."""
        return [c.strip() for c in self.RAW_COURSE_ID.split(",") if c.strip()]

config = Config()
