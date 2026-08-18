import os
import sys
from typing import Dict, Any
from playwright.sync_api import sync_playwright, Page, BrowserContext
from app.config import config


class MoodleService:
    def __init__(self):
        self.base_url = config.MOODLE_BASE_URL
        self.username = config.MOODLE_USER
        self.password = config.MOODLE_PASS
        self.default_course_id = config.DEFAULT_COURSE_ID
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
        self, page: Page, item: Dict[str, Any], course_id: str = None
    ) -> None:
        """Crea un módulo de recurso URL en la sección y curso especificados."""
        target_course = course_id or item.get("course_id") or self.default_course_id
        seccion = item.get("seccion", 0)
        nombre = item.get("nombre") or item.get("titulo", "Nuevo Recurso URL")
        url = item.get("url")

        print(f"Publicando URL en Curso {target_course} (Sección {seccion}): '{nombre}'...")

        url_crear = (
            f"{self.base_url}/course/modedit.php?"
            f"add=url&type=&course={target_course}&section={seccion}&return=0"
        )
        page.goto(url_crear)
        page.wait_for_load_state("domcontentloaded")

        page.fill("#id_name", nombre)
        page.fill("#id_externalurl", url)

        page.click("#id_submitbutton2")
        page.wait_for_load_state("networkidle")
        print(f"Recurso '{nombre}' publicado exitosamente.")

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
        print(f"Anuncio '{asunto}' publicado en el foro exitosamente.")

    def publish_item(self, item: Dict[str, Any], course_id: str = None) -> None:
        """Ejecuta una publicación individual abriendo un navegador Playwright."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            if os.path.exists(self.session_file):
                context = browser.new_context(storage_state=self.session_file)
            else:
                context = browser.new_context()

            page = context.new_page()
            self.ensure_authenticated(page, context)

            tipo = item.get("tipo", "recurso_url")
            if tipo == "recurso_url":
                self.publish_url_resource(page, item, course_id)
            elif tipo == "anuncio_foro":
                self.publish_forum_announcement(page, item)
            else:
                raise ValueError(f"Tipo de recurso desconocido: {tipo}")

            browser.close()
