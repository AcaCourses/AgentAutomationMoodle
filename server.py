import uvicorn
from fastapi import FastAPI, HTTPException, Header
from app.config import config
from app.models import LinkedInPayload
from app.services.ai_service import AIService
from app.services.moodle_service import MoodleService
from app.services.ngrok_service import setup_ngrok_tunnel

app = FastAPI(
    title="Agente Moodle SEA Acatlán API",
    description="API Webhook para transformar publicaciones técnicas y subirlas automáticamente a Moodle.",
    version="2.0.0",
)

ai_service = AIService()
moodle_service = MoodleService()


@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "Agente Moodle SEA Acatlán API",
        "version": "2.0.0",
    }


@app.post("/webhook-linkedin")
def webhook_linkedin(payload: LinkedInPayload, x_token: str = Header(None)):
    if x_token != config.API_SECRET:
        raise HTTPException(
            status_code=401, detail="Token inválido. Verifica el encabezado x-token."
        )

    if not config.MOODLE_USER or not config.MOODLE_PASS or config.MOODLE_USER == "tu_usuario_o_correo":
        raise HTTPException(
            status_code=500,
            detail="Las credenciales de Moodle no están configuradas en el archivo .env",
        )

    # 1. Transformación inteligente con Hugging Face (Qwen2.5-72B)
    datos_ia = ai_service.adapt_linkedin_post(payload.texto, payload.url)
    seccion = payload.seccion or datos_ia.get("seccion", 0)
    target_course_id = payload.course_id or config.DEFAULT_COURSE_ID

    item_recurso = {
        "tipo": "recurso_url",
        "nombre": datos_ia.get("titulo", "Recurso LinkedIn"),
        "url": payload.url,
        "seccion": seccion,
        "course_id": target_course_id,
    }

    # 2. Publicación directa en Moodle con Playwright
    try:
        moodle_service.publish_item(item_recurso, course_id=target_course_id)
        return {
            "status": "ok",
            "publicado": datos_ia.get("titulo"),
            "course_id": target_course_id,
            "seccion": seccion,
            "datos_ia": datos_ia,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error al publicar en Moodle: {str(e)}"
        )


if __name__ == "__main__":
    port = 8000
    setup_ngrok_tunnel(port)
    uvicorn.run(app, host="0.0.0.0", port=port)
