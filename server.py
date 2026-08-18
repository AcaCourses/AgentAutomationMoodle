import json
import re
import uvicorn
from fastapi import FastAPI, HTTPException, Header, Request, Response
from app.config import config
from app.models import LinkedInPayload
from app.services.ai_service import AIService
from app.services.moodle_service import MoodleService
from app.services.ngrok_service import setup_ngrok_tunnel

app = FastAPI(
    title="Agente Moodle SEA Acatlán API",
    description="API Webhook para clasificar publicaciones técnicas y subirlas automáticamente a Moodle con incrustación de publicaciones de LinkedIn (Iframe) y logos oficiales.",
    version="2.0.0",
)

ai_service = AIService()
moodle_service = MoodleService()


@app.middleware("http")
async def sanitize_raw_json_middleware(request: Request, call_next):
    """
    Middleware para sanitizar cuerpos JSON entrantes que contengan saltos de línea crudos
    sin escapar (evitando el error 422 'Invalid control character at' en cURL/Swagger).
    """
    if request.method in ["POST", "PUT", "PATCH"]:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body_bytes = await request.body()
                if body_bytes:
                    body_str = body_bytes.decode("utf-8", errors="ignore")
                    # Si el JSON no puede ser decodificado directamente por tener saltos de línea crudos
                    try:
                        json.loads(body_str)
                    except json.JSONDecodeError:
                        # Reemplazar saltos de línea crudos dentro de las cadenas por \n escapados
                        sanitized_body = re.sub(r'[\r\n]+', r'\\n', body_str)
                        async def receive():
                            return {"type": "http.request", "body": sanitized_body.encode("utf-8")}
                        request = Request(request.scope, receive=receive)
            except Exception as e:
                print(f"Aviso en middleware de sanitización JSON: {e}")

    response = await call_next(request)
    return response


@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "Agente Moodle SEA Acatlán API",
        "version": "2.0.0",
        "cursos_configurados": config.COURSE_IDS,
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

    # Sanitizar placeholder 'string' si proviene de Swagger UI
    linkedin_url = payload.linkedin_url
    if linkedin_url and linkedin_url.strip().lower() in ["string", "null", "none", ""]:
        linkedin_url = None

    target_course_id = payload.course_id
    if target_course_id is None or str(target_course_id).strip().lower() in ["string", "null", "none", ""]:
        target_course_id = config.COURSE_IDS

    # 1. Clasificación inteligente y enriquecimiento (soporta 'empresa' y 'linkedin_url' opcional)
    datos_ia = ai_service.adapt_linkedin_post(
        payload.texto, payload.url, payload.empresa, linkedin_url
    )

    item_recurso = {
        "tipo": "recurso_url",
        "nombre": datos_ia.get("nombre", "Recurso Destacado"),
        "categoria_moodle": datos_ia.get("categoria_moodle", "Recursos"),
        "descripcion_html": datos_ia.get("descripcion_html", ""),
        "url": payload.url,
        "seccion": payload.seccion if payload.seccion != 0 else None,
    }

    # 2. Publicación directa en Moodle con Playwright en la sección seleccionada
    try:
        cursos_publicados = moodle_service.publish_item(item_recurso, course_id=target_course_id)
        return {
            "status": "ok",
            "publicado": datos_ia.get("nombre"),
            "empresa": datos_ia.get("empresa"),
            "categoria_moodle": datos_ia.get("categoria_moodle"),
            "cursos_afectados": cursos_publicados,
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
