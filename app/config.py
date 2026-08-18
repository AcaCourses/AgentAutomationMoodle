import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    MOODLE_BASE_URL: str = os.getenv("MOODLE_BASE_URL", "https://sea.acatlan.unam.mx").rstrip("/")
    MOODLE_USER: str = os.getenv("MOODLE_USER", "")
    MOODLE_PASS: str = os.getenv("MOODLE_PASS", "")
    DEFAULT_COURSE_ID: str = os.getenv("MOODLE_COURSE_ID", "22842")
    
    API_SECRET: str = os.getenv("API_SECRET", "mi_clave_secreta")
    HF_TOKEN: str = os.getenv("HF_TOKEN", "")
    NGROK_AUTHTOKEN: str = os.getenv("NGROK_AUTHTOKEN", "")
    
    SESSION_FILE: str = "session.json"
    JSON_DATA_FILE: str = "recursos.json"
    HF_MODEL: str = "Qwen/Qwen2.5-72B-Instruct"

config = Config()
