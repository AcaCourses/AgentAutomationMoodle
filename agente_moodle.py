import os
import json
import sys
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

BASE_URL = os.getenv("MOODLE_BASE_URL", "https://sea.acatlan.unam.mx").rstrip("/")
USERNAME = os.getenv("MOODLE_USER")
PASSWORD = os.getenv("MOODLE_PASS")
COURSE_ID = os.getenv("MOODLE_COURSE_ID")
SESSION_FILE = "session.json"
JSON_DATA_FILE = "recursos.json"


def login_and_save_session(page, context):
    """Inicia sesión en Moodle y guarda el estado de cookies/sesión."""
    print("Iniciando sesión en SEA Acatlán...")
    page.goto(f"{BASE_URL}/login/index.php")
    
    page.fill("#username", USERNAME)
    page.fill("#password", PASSWORD)
    page.click("#loginbtn")
    page.wait_for_load_state("networkidle")

    # Verificar si el login fue exitoso comprobando la URL o un selector clave
    if "login" in page.url:
        print("Error: No se pudo iniciar sesión. Revisa tus credenciales en el archivo .env")
        sys.exit(1)

    context.storage_state(path=SESSION_FILE)
    print("Sesión guardada exitosamente en session.json.")


def publicar_recurso_url(page, item):
    """Crea una actividad de tipo URL en el curso de Moodle 4.x."""
    seccion = item.get("seccion", 0)
    course_id = item.get("course_id", COURSE_ID)
    print(f"Publicando URL en curso {course_id}: '{item['nombre']}'...")

    # URL directa de Moodle para agregar módulo tipo URL
    url_crear = (
        f"{BASE_URL}/course/modedit.php?add=url&type=&course={course_id}&section={seccion}&return=0"
    )
    page.goto(url_crear)
    page.wait_for_load_state("domcontentloaded")

    # Llenar nombre del recurso y URL externa
    page.fill("#id_name", item["nombre"])
    page.fill("#id_externalurl", item["url"])

    # Clic en 'Guardar cambios y regresar al curso'
    page.click("#id_submitbutton2")
    page.wait_for_load_state("networkidle")
    print(f"Recurso '{item['nombre']}' publicado correctamente.")


def publicar_anuncio_foro(page, item):
    """Publica un nuevo tema en el foro de avisos."""
    forum_id = item.get("forum_id")
    print(f"Publicando anuncio: '{item['asunto']}'...")

    page.goto(f"{BASE_URL}/mod/forum/post.php?forum={forum_id}")
    page.wait_for_load_state("domcontentloaded")

    page.fill("#id_subject", item["asunto"])

    # Soporte para editor TinyMCE o Atto en Moodle 4.x
    editor = page.locator('[contenteditable="true"]')
    if editor.count() > 0:
        editor.first.fill(item["mensaje"])
    else:
        page.fill("#id_message", item["mensaje"])

    page.click("#id_submitbutton")
    page.wait_for_load_state("networkidle")
    print(f"Anuncio '{item['asunto']}' publicado en el foro.")


def main():
    if not USERNAME or not PASSWORD or USERNAME == "tu_usuario_o_correo":
        print("Configuración pendiente: Por favor edita el archivo .env con tus credenciales reales (MOODLE_USER y MOODLE_PASS).")
        return

    if not os.path.exists(JSON_DATA_FILE):
        print(f"Error: No se encontró el archivo de datos {JSON_DATA_FILE}")
        return

    with open(JSON_DATA_FILE, "r", encoding="utf-8") as f:
        recursos = json.load(f)

    # Filtrar si hay tareas pendientes
    pendientes = [item for item in recursos if not item.get("publicado")]
    if not pendientes:
        print("No hay recursos pendientes por publicar en recursos.json.")
        return

    print(f"Se encontraron {len(pendientes)} elemento(s) pendiente(s) por publicar.")

    with sync_playwright() as p:
        # headless=True para ejecución silenciosa (cambia a False si deseas ver el navegador)
        browser = p.chromium.launch(headless=True)

        # Reutilizar sesión si existe
        if os.path.exists(SESSION_FILE):
            context = browser.new_context(storage_state=SESSION_FILE)
        else:
            context = browser.new_context()

        page = context.new_page()

        # Verificar si la sesión es válida o requiere login
        page.goto(f"{BASE_URL}/my/")
        if "login" in page.url:
            login_and_save_session(page, context)

        # Procesar elementos pendientes
        actualizados = False
        for item in recursos:
            if item.get("publicado"):
                continue

            try:
                if item["tipo"] == "recurso_url":
                    publicar_recurso_url(page, item)
                    item["publicado"] = True
                    actualizados = True
                elif item["tipo"] == "anuncio_foro":
                    publicar_anuncio_foro(page, item)
                    item["publicado"] = True
                    actualizados = True
            except Exception as e:
                print(f"Error publicando '{item.get('nombre') or item.get('asunto')}': {e}")

        # Guardar estado actualizado en el JSON
        if actualizados:
            with open(JSON_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(recursos, f, indent=2, ensure_ascii=False)
            print("Archivo recursos.json actualizado con éxito.")

        browser.close()


if __name__ == "__main__":
    main()
