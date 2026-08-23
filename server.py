import asyncio
import json
import os
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
from app.models import LinkedInPayload, ChatPayload
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


@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    if request.method == "OPTIONS":
        response = Response(status_code=200)
    else:
        try:
            response = await call_next(request)
        except Exception as e:
            response = Response(content=json.dumps({"detail": str(e)}), status_code=500, media_type="application/json")
    
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Expose-Headers"] = "*"
    return response


@app.options("/{full_path:path}")
def options_handler(full_path: str):
    return Response(status_code=200)


@app.options("/")
def options_root():
    return Response(status_code=200)


@app.api_route("/", methods=["GET", "HEAD"])
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
    categoria_det = datos_ia.get("categoria_moodle", "Recursos")
    log_cb(f"✅ Análisis IA completado: '{datos_ia.get('nombre')}' ({categoria_det})", "success")

    tipo_item = "tarea_assign" if categoria_det == "Tareas" else "recurso_url"

    item_recurso = {
        "tipo": tipo_item,
        "nombre": datos_ia.get("nombre", "Recurso Destacado"),
        "categoria_moodle": categoria_det,
        "descripcion_html": datos_ia.get("descripcion_html", ""),
        "url": payload.url,
        "seccion": payload.seccion if payload.seccion != 0 else None,
        "dias_entrega": 15,
    }

    try:
        cursos_publicados = moodle_service.publish_item(item_recurso, course_id=target_course_id, log_cb=log_cb)
        return {
            "status": "ok",
            "publicado": datos_ia.get("nombre"),
            "empresa": datos_ia.get("empresa"),
            "categoria_moodle": categoria_det,
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
            categoria_det = datos_ia.get("categoria_moodle", "Recursos")
            send_log(f"🧠 Clasificado como: '{datos_ia.get('nombre')}' | Categoría: '{categoria_det}'", "success")

            tipo_item = "tarea_assign" if categoria_det == "Tareas" else "recurso_url"

            item_recurso = {
                "tipo": tipo_item,
                "nombre": datos_ia.get("nombre", "Recurso Destacado"),
                "categoria_moodle": categoria_det,
                "descripcion_html": datos_ia.get("descripcion_html", ""),
                "url": payload.url,
                "seccion": payload.seccion if payload.seccion != 0 else None,
                "dias_entrega": 15,
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


@app.post("/webhook-chat-stream")
async def webhook_chat_stream(payload: ChatPayload, x_token: str = Header(None)):
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
            send_log("🤖 Modi recibió tu mensaje. Analizando contenido e intenciones...", "info")
            parsed_chat = ai_service.parse_chat_message(payload.message, cb=send_log)

            texto = parsed_chat.get("texto", payload.message)
            url = parsed_chat.get("url")
            linkedin_url = parsed_chat.get("linkedin_url")
            empresa = parsed_chat.get("empresa")

            # Resolver curso
            target_course_id = payload.course_id or parsed_chat.get("course_id")
            if target_course_id is None or str(target_course_id).strip().lower() in ["string", "null", "none", ""]:
                target_course_id = config.COURSE_IDS

            seccion = payload.seccion if payload.seccion is not None else parsed_chat.get("seccion", 0)

            send_log("🤖 Generando contenido formativo y clasificando con IA...", "info")
            datos_ia = ai_service.adapt_linkedin_post(
                texto, url, empresa, linkedin_url, cb=send_log
            )
            categoria_det = datos_ia.get("categoria_moodle", "Recursos")

            # Enviar previsualización temprana al cliente
            preview_info = {
                "nombre": datos_ia.get("nombre", "Recurso Destacado"),
                "empresa": datos_ia.get("empresa"),
                "categoria_moodle": categoria_det,
                "url": url,
                "linkedin_url": linkedin_url,
                "course_id": target_course_id,
                "seccion": seccion
            }
            event_queue.put({"type": "preview", "data": preview_info})

            send_log(f"🧠 Modi clasificó el elemento como: '{datos_ia.get('nombre')}' ({categoria_det})", "success")

            tipo_item = "tarea_assign" if categoria_det == "Tareas" else "recurso_url"

            item_recurso = {
                "tipo": tipo_item,
                "nombre": datos_ia.get("nombre", "Recurso Destacado"),
                "categoria_moodle": categoria_det,
                "descripcion_html": datos_ia.get("descripcion_html", ""),
                "url": url,
                "seccion": seccion if seccion != 0 else None,
                "dias_entrega": 15,
            }

            send_log("🎭 Iniciando automatización con Playwright en Moodle SEA Acatlán...", "info")
            cursos_publicados = moodle_service.publish_item(item_recurso, course_id=target_course_id, log_cb=send_log)

            result = {
                "status": "ok",
                "publicado": datos_ia.get("nombre"),
                "empresa": datos_ia.get("empresa"),
                "categoria_moodle": datos_ia.get("categoria_moodle"),
                "cursos_afectados": cursos_publicados,
                "datos_ia": datos_ia,
                "parsed_chat": parsed_chat,
            }
            event_queue.put({"type": "result", "data": result})
        except Exception as e:
            send_log(f"❌ Error durante la automatización: {str(e)}", "error")
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
    port = int(os.environ.get("PORT", 8000))
    # Solo iniciar túnel Ngrok en entorno local (Render define la variable RENDER=true)
    if not os.environ.get("RENDER"):
        setup_ngrok_tunnel(port)
    uvicorn.run(app, host="0.0.0.0", port=port)

