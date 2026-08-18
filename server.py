import os
import json
import sys
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from huggingface_hub import InferenceClient
from playwright.sync_api import sync_playwright
from pyngrok import ngrok
import uvicorn

load_dotenv()

BASE_URL = os.getenv("MOODLE_BASE_URL", "https://sea.acatlan.unam.mx").rstrip("/")
USERNAME = os.getenv("MOODLE_USER")
PASSWORD = os.getenv("MOODLE_PASS")
COURSE_ID = os.getenv("MOODLE_COURSE_ID", "22842")
API_SECRET = os.getenv("API_SECRET", "mi_clave_secreta")
HF_TOKEN = os.getenv("HF_TOKEN")
NGROK_AUTHTOKEN = os.getenv("NGROK_AUTHTOKEN")
SESSION_FILE = "session.json"

# Cliente Hugging Face
hf_client = InferenceClient(model="Qwen/Qwen2.5-72B-Instruct", token=HF_TOKEN) if HF_TOKEN else None

SYSTEM_PROMPT = """Eres un asistente académico para un profesor de Matemáticas Aplicadas y Computación en FES Acatlán.
Recibes una publicación técnica de LinkedIn y debes adaptarla para Moodle.
Responde ÚNICAMENTE un JSON válido con esta estructura exacta:
{
  "tipo": "recurso_url",
  "titulo": "Título profesional y claro",
  "contenido_html": "<p>Breve contexto educativo para los estudiantes.</p>",
  "seccion": 0
}
"""

def procesar_post_ia(texto: str, url: str) -> dict:
    if not hf_client:
        # Fallback en caso de no tener HF_TOKEN configurado aún
        return {
            "tipo": "recurso_url",
            "titulo": f"Recurso: {texto[:40]}...",
            "contenido_html": f"<p>{texto}</p>",
            "seccion": 0,
            "url": url
        }
    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Post de LinkedIn:\n\"\"\"{texto}\"\"\"\nEnlace: {url}"}
        ]
        res = hf_client.chat_completion(messages=messages, max_tokens=600, temperature=0.2)
        raw = res.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```json")[-1].split("```")[0].strip()
        data = json.loads(raw)
        data["url"] = url
        return data
    except Exception as e:
        print(f"Error procesando con Hugging Face: {e}")
        return {
            "tipo": "recurso_url",
            "titulo": f"Recurso sobre IA / Computación",
            "contenido_html": f"<p>{texto}</p>",
            "seccion": 0,
            "url": url
        }

app = FastAPI(title="Agente Moodle SEA Acatlán API")

class LinkedInPayload(BaseModel):
    texto: str
    url: str
    seccion: Optional[int] = 0
    course_id: Optional[str] = None

@app.get("/")
def read_root():
    return {"status": "online", "message": "Servidor Agente Moodle con Hugging Face y Playwright activo."}

@app.post("/webhook-linkedin")
def webhook_linkedin(payload: LinkedInPayload, x_token: str = Header(None)):
    if x_token != API_SECRET:
        raise HTTPException(status_code=401, detail="Token inválido. Verifica el encabezado x-token.")

    if not USERNAME or not PASSWORD or USERNAME == "tu_usuario_o_correo":
        raise HTTPException(
            status_code=500,
            detail="Las credenciales de Moodle no están configuradas en el archivo .env"
        )

    # 1. Transformación con Hugging Face
    datos = procesar_post_ia(payload.texto, payload.url)
    seccion = payload.seccion or datos.get("seccion", 0)
    target_course_id = payload.course_id or COURSE_ID

    # 2. Publicación directa en Moodle con Playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            
            if os.path.exists(SESSION_FILE):
                context = browser.new_context(storage_state=SESSION_FILE)
            else:
                context = browser.new_context()

            page = context.new_page()

            # Verificación / Login
            page.goto(f"{BASE_URL}/my/")
            if "login" in page.url:
                print("Iniciando sesión en Moodle...")
                page.goto(f"{BASE_URL}/login/index.php")
                page.fill("#username", USERNAME)
                page.fill("#password", PASSWORD)
                page.click("#loginbtn")
                page.wait_for_load_state("networkidle")
                context.storage_state(path=SESSION_FILE)

            # Crear Recurso URL en Moodle 4.x
            url_crear = f"{BASE_URL}/course/modedit.php?add=url&type=&course={target_course_id}&section={seccion}&return=0"
            page.goto(url_crear)
            page.wait_for_load_state("domcontentloaded")
            
            page.fill("#id_name", datos["titulo"])
            page.fill("#id_externalurl", datos["url"])

            # Guardar cambios y regresar al curso
            page.click("#id_submitbutton2")
            page.wait_for_load_state("networkidle")
            browser.close()

        return {"status": "ok", "publicado": datos["titulo"], "datos_ia": datos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al publicar en Moodle con Playwright: {str(e)}")

if __name__ == "__main__":
    port = 8000
    # Autenticar ngrok y abrir túnel
    if NGROK_AUTHTOKEN and NGROK_AUTHTOKEN != "tu_ngrok_authtoken":
        try:
            ngrok.set_auth_token(NGROK_AUTHTOKEN)
            tunnel = ngrok.connect(port)
            print(f"\n🚀 TU URL PÚBLICA DE NGROK ES: {tunnel.public_url}")
            print(f"👉 Endpoint listo: {tunnel.public_url}/webhook-linkedin\n")
        except Exception as e:
            print(f"Aviso Ngrok: {e}")
    else:
        print(f"\n💡 Ngrok no configurado. El servidor local correrá en http://localhost:{port}")
        print(f"👉 Endpoint local: http://localhost:{port}/webhook-linkedin\n")

    uvicorn.run(app, host="0.0.0.0", port=port)
