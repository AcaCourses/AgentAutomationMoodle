import asyncio
import json
import queue
import re
import threading
import uvicorn
from typing import Callable
from fastapi import FastAPI, HTTPException, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute

from app.config import config
from app.models import LinkedInPayload
from app.services.ai_service import AIService
from app.services.moodle_service import MoodleService
from app.services.ngrok_service import setup_ngrok_tunnel


class SanitizedJSONRoute(APIRoute):
    """
    Ruta personalizada de FastAPI que intercepta la petición HTTP y parsea
    el JSON permitiendo saltos de línea crudos sin escapar (strict=False),
    evitando el error 422 'Invalid control character at' de cURL o Swagger UI.
    """
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            if request.method in ["POST", "PUT", "PATCH"]:
                content_type = request.headers.get("content-type", "")
                if "application/json" in content_type:
                    try:
                        body_bytes = await request.body()
                        if body_bytes:
                            body_str = body_bytes.decode("utf-8", errors="ignore")
                            parsed_data = json.loads(body_str, strict=False)
                            sanitized_bytes = json.dumps(parsed_data).encode("utf-8")

                            async def receive():
                                return {"type": "http.request", "body": sanitized_bytes}

                            request = Request(request.scope, receive=receive)
                    except Exception as e:
                        print(f"Aviso al sanitizar cuerpo JSON: {e}")

            return await original_route_handler(request)

        return custom_route_handler


app = FastAPI(
    title="Moodi - Agente Moodle SEA Acatlán API",
    description="API Webhook de Moodi para clasificar publicaciones técnicas y subirlas automáticamente a Moodle con incrustación de publicaciones de LinkedIn (Iframe) y logos oficiales.",
    version="2.0.0",
)
app.router.route_class = SanitizedJSONRoute

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

ai_service = AIService()
moodle_service = MoodleService()


@app.options("/{full_path:path}")
def options_handler(full_path: str):
    return Response(status_code=200)


@app.options("/")
def options_root():
    return Response(status_code=200)


@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "Moodi - Agente Moodle SEA Acatlán API",
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

    logs = []
    def log_cb(msg: str, level: str = "info"):
        logs.append({"timestamp": asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0, "message": msg, "level": level})

    linkedin_url = payload.linkedin_url
    if linkedin_url and linkedin_url.strip().lower() in ["string", "null", "none", ""]:
        linkedin_url = None

    target_course_id = payload.course_id
    if target_course_id is None or str(target_course_id).strip().lower() in ["string", "null", "none", ""]:
        target_course_id = config.COURSE_IDS

    log_cb("🤖 Analizando publicación y consultando IA...", "info")
    datos_ia = ai_service.adapt_linkedin_post(
        payload.texto, payload.url, payload.empresa, linkedin_url, cb=log_cb
    )
    log_cb(f"✅ Análisis IA completado: '{datos_ia.get('nombre')}' ({datos_ia.get('categoria_moodle')})", "success")

    item_recurso = {
        "tipo": "recurso_url",
        "nombre": datos_ia.get("nombre", "Recurso Destacado"),
        "categoria_moodle": datos_ia.get("categoria_moodle", "Recursos"),
        "descripcion_html": datos_ia.get("descripcion_html", ""),
        "url": payload.url,
        "seccion": payload.seccion if payload.seccion != 0 else None,
    }

    try:
        cursos_publicados = moodle_service.publish_item(item_recurso, course_id=target_course_id, log_cb=log_cb)
        return {
            "status": "ok",
            "publicado": datos_ia.get("nombre"),
            "empresa": datos_ia.get("empresa"),
            "categoria_moodle": datos_ia.get("categoria_moodle"),
            "cursos_afectados": cursos_publicados,
            "datos_ia": datos_ia,
            "logs": logs,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error al publicar en Moodle: {str(e)}"
        )


@app.post("/webhook-linkedin-stream")
async def webhook_linkedin_stream(payload: LinkedInPayload, x_token: str = Header(None)):
    if x_token != config.API_SECRET:
        raise HTTPException(
            status_code=401, detail="Token inválido. Verifica el encabezado x-token."
        )

    if not config.MOODLE_USER or not config.MOODLE_PASS or config.MOODLE_USER == "tu_usuario_o_correo":
        raise HTTPException(
            status_code=500,
            detail="Las credenciales de Moodle no están configuradas en el archivo .env",
        )

    event_queue = queue.Queue()

    def send_log(msg: str, level: str = "info"):
        event_queue.put({"type": "log", "message": msg, "level": level})

    def worker():
        try:
            linkedin_url = payload.linkedin_url
            if linkedin_url and linkedin_url.strip().lower() in ["string", "null", "none", ""]:
                linkedin_url = None

            target_course_id = payload.course_id
            if target_course_id is None or str(target_course_id).strip().lower() in ["string", "null", "none", ""]:
                target_course_id = config.COURSE_IDS

            send_log("🤖 Procesando publicación y clasificando contenido con IA...", "info")
            datos_ia = ai_service.adapt_linkedin_post(
                payload.texto, payload.url, payload.empresa, linkedin_url, cb=send_log
            )
            send_log(f"🧠 Clasificado como: '{datos_ia.get('nombre')}' | Categoría: '{datos_ia.get('categoria_moodle')}'", "success")

            item_recurso = {
                "tipo": "recurso_url",
                "nombre": datos_ia.get("nombre", "Recurso Destacado"),
                "categoria_moodle": datos_ia.get("categoria_moodle", "Recursos"),
                "descripcion_html": datos_ia.get("descripcion_html", ""),
                "url": payload.url,
                "seccion": payload.seccion if payload.seccion != 0 else None,
            }

            cursos_publicados = moodle_service.publish_item(item_recurso, course_id=target_course_id, log_cb=send_log)

            result = {
                "status": "ok",
                "publicado": datos_ia.get("nombre"),
                "empresa": datos_ia.get("empresa"),
                "categoria_moodle": datos_ia.get("categoria_moodle"),
                "cursos_afectados": cursos_publicados,
                "datos_ia": datos_ia,
            }
            event_queue.put({"type": "result", "data": result})
        except Exception as e:
            send_log(f"❌ Error en automatización: {str(e)}", "error")
            event_queue.put({"type": "error", "detail": str(e)})
        finally:
            event_queue.put(None)

    threading.Thread(target=worker, daemon=True).start()

    async def event_generator():
        while True:
            try:
                item = event_queue.get_nowait()
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
            except queue.Empty:
                await asyncio.sleep(0.1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    port = 8000
    setup_ngrok_tunnel(port)
    uvicorn.run(app, host="0.0.0.0", port=port)
