import os
import sys
from typing import Dict, Any, List, Union
from playwright.sync_api import sync_playwright, Page, BrowserContext
from app.config import config


class MoodleService:
    def __init__(self):
        self.base_url = config.MOODLE_BASE_URL
        self.username = config.MOODLE_USER
        self.password = config.MOODLE_PASS
        self.default_courses = config.COURSE_IDS
        self.session_file = config.SESSION_FILE

    def login_and_save_session(self, page: Page, context: BrowserContext) -> None:
        """Autentica al usuario en Moodle SEA Acatlán y guarda el estado en session.json."""
        print("Iniciando sesión en SEA Acatlán...")
        page.goto(f"{self.base_url}/login/index.php")

        page.fill("#username", self.username)
        page.fill("#password", self.password)
        page.click("#loginbtn")
        page.wait_for_load_state("networkidle")

        if "login" in page.url:
            raise ValueError("Credenciales inválidas o error de inicio de sesión en Moodle.")

        context.storage_state(path=self.session_file)
        print("Sesión guardada exitosamente.")

    def ensure_authenticated(self, page: Page, context: BrowserContext) -> None:
        """Verifica si la sesión actual es válida o ejecuta el login si expiró."""
        page.goto(f"{self.base_url}/my/")
        if "login" in page.url:
            self.login_and_save_session(page, context)

    def publish_url_resource(
        self, page: Page, item: Dict[str, Any], course_id: str
    ) -> None:
        """
        Crea un módulo de recurso URL en la pestaña Recursos y sección del curso especificado.
        Rena los campos: Nombre, URL externa, Descripción enriquecida por la IA y
        marca la casilla 'Mostrar descripción en la página del curso'.
        """
        seccion = item.get("seccion", 0)
        nombre = item.get("nombre") or item.get("titulo", "Nuevo Recurso URL")
        url = item.get("url")
        descripcion_html = item.get("descripcion_html") or item.get("contenido_html", "")

        print(f"Navegando al Curso {course_id}...")
        # 1. Ir a la vista principal del curso para asegurar contexto
        page.goto(f"{self.base_url}/course/view.php?id={course_id}")
        page.wait_for_load_state("domcontentloaded")

        # 2. Intentar activar 'Modo de edición' si la palanca está presente
        try:
            edit_switch = page.locator('input[name="setmode"], .editmode-switch input')
            if edit_switch.count() > 0 and not edit_switch.first.is_checked():
                print("Activando 'Modo de edición'...")
                edit_switch.first.click()
                page.wait_for_load_state("networkidle")
        except Exception as e:
            print(f"Modo de edición aviso: {e}")

        # 3. Navegar al formulario de creación 'Nueva URL' para la sección indicada
        print(f"Publicando URL en Curso {course_id} (Sección {seccion}): '{nombre}'...")
        url_crear = (
            f"{self.base_url}/course/modedit.php?"
            f"add=url&type=&course={course_id}&section={seccion}&return=0"
        )
        page.goto(url_crear)
        page.wait_for_load_state("domcontentloaded")

        # 4. Llenar Nombre
        page.fill("#id_name", nombre)

        # 5. Llenar URL externa
        page.fill("#id_externalurl", url)

        # 6. Llenar Descripción enriquecida por la IA (soporta TinyMCE / Atto rich editor)
        if descripcion_html:
            print("Insertando descripción enriquecida por IA...")
            editor = page.locator('[contenteditable="true"], #id_introeditor_editable')
            if editor.count() > 0:
                editor.first.fill(descripcion_html)
            else:
                try:
                    page.fill("#id_introeditor", descripcion_html)
                except Exception:
                    pass

        # 7. Marcar casilla 'Mostrar descripción en la página del curso' si está disponible
        try:
            show_desc = page.locator("#id_showdescription")
            if show_desc.count() > 0 and not show_desc.is_checked():
                show_desc.check()
                print("Casilla 'Mostrar descripción en la página del curso' activada.")
        except Exception as e:
            print(f"Aviso al activar casilla descripción: {e}")

        # 8. Clic en 'Guardar cambios y regresar al curso'
        page.click("#id_submitbutton2")
        page.wait_for_load_state("networkidle")
        print(f"✅ Recurso '{nombre}' publicado con éxito en el curso {course_id}.")

    def publish_forum_announcement(
        self, page: Page, item: Dict[str, Any]
    ) -> None:
        """Publica un anuncio en el foro especificado."""
        forum_id = item.get("forum_id")
        asunto = item.get("asunto", "Nuevo Anuncio")
        mensaje = item.get("mensaje", "")

        print(f"Publicando anuncio en Foro {forum_id}: '{asunto}'...")
        page.goto(f"{self.base_url}/mod/forum/post.php?forum={forum_id}")
        page.wait_for_load_state("domcontentloaded")

        page.fill("#id_subject", asunto)

        editor = page.locator('[contenteditable="true"]')
        if editor.count() > 0:
            editor.first.fill(mensaje)
        else:
            page.fill("#id_message", mensaje)

        page.click("#id_submitbutton")
        page.wait_for_load_state("networkidle")
        print(f"✅ Anuncio '{asunto}' publicado en el foro exitosamente.")

    def resolve_target_courses(self, target: Any) -> List[str]:
        """Resuelve uno o múltiples IDs de cursos."""
        if not target:
            return self.default_courses
        if isinstance(target, list):
            return [str(c) for c in target]
        if isinstance(target, str) and "," in target:
            return [c.strip() for c in target.split(",") if c.strip()]
        return [str(target)]

    def publish_item(self, item: Dict[str, Any], course_id: Any = None) -> List[str]:
        """
        Publica un ítem en uno o varios cursos de manera secuencial (uno tras otro).
        """
        courses = self.resolve_target_courses(course_id or item.get("course_id") or item.get("courses"))
        published_courses = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            if os.path.exists(self.session_file):
                context = browser.new_context(storage_state=self.session_file)
            else:
                context = browser.new_context()

            page = context.new_page()
            self.ensure_authenticated(page, context)

            tipo = item.get("tipo", "recurso_url")

            for cid in courses:
                if tipo == "recurso_url":
                    self.publish_url_resource(page, item, course_id=cid)
                    published_courses.append(cid)
                elif tipo == "anuncio_foro":
                    self.publish_forum_announcement(page, item)
                    published_courses.append(cid)
                else:
                    raise ValueError(f"Tipo de recurso desconocido: {tipo}")

            browser.close()

        return published_courses
