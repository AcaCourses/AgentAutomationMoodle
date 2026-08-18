import os
import sys
import re
import subprocess
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

    def take_debug_screenshot(self, page: Page, name: str = "debug_screenshot.png") -> str:
        """Captura una captura de pantalla del estado actual para depuración."""
        try:
            os.makedirs("debug", exist_ok=True)
            path = os.path.join("debug", name)
            page.screenshot(path=path, full_page=True)
            print(f"📸 Captura de pantalla guardada en: {os.path.abspath(path)}")
            return path
        except Exception as e:
            print(f"No se pudo guardar la captura de pantalla: {e}")
            return ""

    def login_and_save_session(self, page: Page, context: BrowserContext) -> None:
        """Autentica al usuario en Moodle SEA Acatlán y guarda la sesión."""
        print(f"Iniciando sesión en SEA Acatlán ({self.base_url}/login/index.php)...")
        page.goto(f"{self.base_url}/login/index.php")

        page.fill("#username", self.username)
        page.fill("#password", self.password)
        page.click("#loginbtn")
        page.wait_for_load_state("networkidle")

        if "login" in page.url:
            self.take_debug_screenshot(page, "error_login.png")
            raise ValueError("Credenciales inválidas o error de inicio de sesión en Moodle. Revisa tu .env")

        context.storage_state(path=self.session_file)
        print("Sesión guardada exitosamente en session.json.")

    def ensure_authenticated(self, page: Page, context: BrowserContext) -> None:
        """Verifica si la sesión actual es válida o ejecuta el login si expiró."""
        print("Verificando sesión existente...")
        page.goto(f"{self.base_url}/my/")
        page.wait_for_load_state("domcontentloaded")
        if "login" in page.url:
            self.login_and_save_session(page, context)

    def navigate_and_find_section(self, page: Page, course_id: str, categoria_nombre: str) -> int:
        """
        Navega al curso, activa 'Modo de edición', busca la pestaña/sección coincidente
        (ej. 'Recursos', 'Eventos', 'Interns & Job Offers') y retorna el índice de la sección.
        """
        print(f"Navegando a la vista principal del Curso {course_id}...")
        page.goto(f"{self.base_url}/course/view.php?id={course_id}")
        page.wait_for_load_state("domcontentloaded")

        # 1. Activar 'Modo de edición' si no está activo
        try:
            edit_switch = page.locator('input[name="setmode"], .editmode-switch input')
            if edit_switch.count() > 0 and not edit_switch.first.is_checked():
                print("Activando 'Modo de edición'...")
                edit_switch.first.click()
                page.wait_for_load_state("networkidle")
                print("Modo de edición activado correctamente.")
        except Exception as e:
            print(f"Aviso al activar Modo de edición: {e}")

        self.take_debug_screenshot(page, f"curso_{course_id}_pestanas.png")

        # 2. Buscar la pestaña/sección correspondiente en la interfaz (ej. "Recursos", "Eventos", "Interns & Job Offers")
        section_index = 0
        section_found = False

        print(f"Buscando la sección '{categoria_nombre}' en las pestañas del curso...")

        # Intentar localizar por enlaces de navegación de sección
        target_tab = page.locator('.nav-tabs a, .nav-link, ul.sections a, div.sectionname a, a[role="tab"]').filter(has_text=categoria_nombre)

        if target_tab.count() > 0:
            href = target_tab.first.get_attribute("href") or ""
            print(f"Pestaña encontrada '{categoria_nombre}' con enlace: {href}")
            
            # Extraer número de sección del href si existe (ej. section=4 o section-4)
            match = re.search(r'section[=\-]?(\d+)', href)
            if match:
                section_index = int(match.group(1))
                section_found = True
                print(f"Índice de sección detectado: {section_index}")

            # Hacer clic en la pestaña para seleccionarla
            try:
                target_tab.first.click()
                page.wait_for_load_state("domcontentloaded")
            except Exception:
                pass

        if not section_found:
            # Búsqueda alternativa por texto en la página
            print(f"Buscando sección '{categoria_nombre}' por selectores secundarios...")
            all_tabs = page.locator('.nav-link, a[role="tab"]').all()
            for idx, tab in enumerate(all_tabs):
                txt = tab.inner_text().strip()
                if categoria_nombre.lower() in txt.lower():
                    section_index = idx
                    section_found = True
                    print(f"Sección '{txt}' identificada en la posición {idx}.")
                    try:
                        tab.click()
                        page.wait_for_load_state("domcontentloaded")
                    except Exception:
                        pass
                    break

        return section_index

    def publish_url_resource(
        self, page: Page, item: Dict[str, Any], course_id: str
    ) -> None:
        """
        Crea un módulo de recurso URL en la sección correspondiente (Recursos, Eventos, Interns & Job Offers).
        Rellena: Nombre, URL externa, Descripción enriquecida en HTML por IA y marca 'Mostrar descripción'.
        """
        categoria = item.get("categoria_moodle") or item.get("categoria") or "Recursos"
        nombre = item.get("nombre") or item.get("titulo", "Nuevo Recurso URL")
        url = item.get("url")
        descripcion_html = item.get("descripcion_html") or item.get("contenido_html", "")

        # 1. Encontrar la sección correspondiente en el curso
        section_index = item.get("seccion") if "seccion" in item and item["seccion"] != 0 else None
        if section_index is None:
            section_index = self.navigate_and_find_section(page, course_id, categoria)

        print(f"Publicando recurso URL en Curso {course_id} | Sección '{categoria}' (id: {section_index})...")

        # 2. Navegar directamente al formulario de creación 'Nueva URL' para dicha sección
        url_crear = (
            f"{self.base_url}/course/modedit.php?"
            f"add=url&type=&course={course_id}&section={section_index}&return=0"
        )
        page.goto(url_crear)
        page.wait_for_load_state("domcontentloaded")

        if "login" in page.url:
            self.take_debug_screenshot(page, "error_sesion_expirada.png")
            raise ValueError("Moodle redirigió a login. Comprueba las credenciales en .env")

        # 3. Llenar Nombre
        try:
            page.wait_for_selector("#id_name", timeout=12000)
            page.fill("#id_name", nombre)
            print(f"Campo Nombre completado: '{nombre}'")
        except Exception as e:
            screenshot_path = self.take_debug_screenshot(page, f"error_nombre_curso_{course_id}.png")
            raise TimeoutError(
                f"No se encontró el campo '#id_name' en Moodle (Página actual: '{page.title()}'). "
                f"Captura guardada en: {screenshot_path}"
            )

        # 4. Llenar URL externa
        page.fill("#id_externalurl", url)
        print(f"Campo URL externa completado: '{url}'")

        # 5. Llenar Descripción enriquecida por IA
        if descripcion_html:
            print("Insertando descripción enriquecida en HTML por IA...")
            editor = page.locator('[contenteditable="true"], #id_introeditor_editable')
            if editor.count() > 0:
                editor.first.fill(descripcion_html)
            else:
                try:
                    page.fill("#id_introeditor", descripcion_html)
                except Exception:
                    pass

        # 6. Marcar casilla 'Mostrar descripción en la página del curso'
        try:
            show_desc = page.locator("#id_showdescription")
            if show_desc.count() > 0 and not show_desc.is_checked():
                show_desc.check()
                print("Casilla 'Mostrar descripción en la página del curso' activada.")
        except Exception as e:
            print(f"Aviso al activar casilla descripción: {e}")

        self.take_debug_screenshot(page, f"formulario_completado_curso_{course_id}.png")

        # 7. Clic en 'Guardar cambios y regresar al curso'
        page.click("#id_submitbutton2")
        page.wait_for_load_state("networkidle")
        print(f"✅ Recurso '{nombre}' publicado con éxito en la sección '{categoria}' del curso {course_id}.")
        self.take_debug_screenshot(page, f"curso_{course_id}_publicado.png")

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
        """Resuelve uno o múltiples IDs de cursos descartando 'string' o valores nulos."""
        if not target or target == "string" or target == ["string"]:
            return self.default_courses
        if isinstance(target, list):
            valid = [str(c).strip() for c in target if str(c).strip() and str(c).strip() != "string"]
            return valid if valid else self.default_courses
        if isinstance(target, str):
            if target.strip() == "string" or not target.strip():
                return self.default_courses
            if "," in target:
                valid = [c.strip() for c in target.split(",") if c.strip() and c.strip() != "string"]
                return valid if valid else self.default_courses
            return [target.strip()]
        return [str(target)]

    def launch_browser_safely(self, p):
        """Intenta lanzar Chromium. Si falta en Codespaces, lo instala automáticamente."""
        try:
            return p.chromium.launch(headless=True)
        except Exception as e:
            if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
                print("Binarios de Chromium no encontrados. Instalando automáticamente...")
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
                return p.chromium.launch(headless=True)
            raise e

    def publish_item(self, item: Dict[str, Any], course_id: Any = None) -> List[str]:
        """
        Publica un ítem en uno o varios cursos de manera secuencial (uno tras otro).
        """
        courses = self.resolve_target_courses(course_id or item.get("course_id") or item.get("courses"))
        published_courses = []

        with sync_playwright() as p:
            browser = self.launch_browser_safely(p)

            if os.path.exists(self.session_file):
                context = browser.new_context(storage_state=self.session_file)
            else:
                context = browser.new_context()

            page = context.new_page()

            try:
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

                # Limpieza automática si todo terminó exitosamente
                if os.path.exists("debug"):
                    import shutil
                    shutil.rmtree("debug", ignore_errors=True)
                    print("🧹 Capturas de pantalla de depuración eliminadas tras ejecución exitosa.")

            except Exception as e:
                screenshot_path = self.take_debug_screenshot(page, "error_ejecucion_general.png")
                print(f"❌ Error en la ejecución: {e}")
                print(f"📸 Revisa la captura en: {os.path.abspath(screenshot_path)}")
                raise e
            finally:
                browser.close()

        return published_courses
