import os
import sys
import re
import datetime
import subprocess
from typing import Dict, Any, List, Union, Optional, Callable
from playwright.sync_api import sync_playwright, Page, BrowserContext
from app.config import config



class MoodleService:
    def __init__(self):
        self.base_url = config.MOODLE_BASE_URL
        self.username = config.MOODLE_USER
        self.password = config.MOODLE_PASS
        self.default_courses = config.COURSE_IDS
        self.session_file = config.SESSION_FILE

    def _log(self, msg: str, level: str = "info", cb: Optional[Callable[[str, str], None]] = None):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] [{level.upper()}] {msg}"
        print(formatted_msg)
        if cb:
            try:
                cb(formatted_msg, level)
            except Exception:
                pass

    def take_debug_screenshot(self, page: Page, name: str = "debug_screenshot.png", cb: Optional[Callable[[str, str], None]] = None) -> str:
        """Registra el estado del navegador en los logs sin tomar fotos para optimizar RAM/CPU y acelerar la ejecución."""
        try:
            url = page.url if page else "N/A"
            title = page.title() if page else "N/A"
            self._log(f"🔍 [Navegador] Estado: '{name}' | URL: {url} | Título: '{title}'", "info", cb)
        except Exception as e:
            self._log(f"Aviso al consultar estado de página ({name}): {e}", "warn", cb)
        return ""

    def login_and_save_session(self, page: Page, context: BrowserContext) -> None:
        """Autentica al usuario en Moodle SEA Acatlán y guarda la sesión."""
        masked_user = f"{self.username[:2]}***{self.username[-2:]}" if len(self.username) > 4 else "***"
        pass_len = len(self.password)
        print(f"🔑 Intentando iniciar sesión en SEA Acatlán ({self.base_url}/login/index.php)...")
        print(f"👤 Usuario configurado: '{masked_user}' (longitud: {len(self.username)}) | Contraseña longitud: {pass_len}")
        page.goto(f"{self.base_url}/login/index.php", wait_until="domcontentloaded")

        page.fill("#username", self.username)
        page.fill("#password", self.password)
        page.click("#loginbtn")
        
        # Esperar activamente la redirección de Moodle fuera de la página de login (hasta 12s para instancias con latencia)
        try:
            page.wait_for_url(lambda u: "login/index.php" not in u.lower(), timeout=12000)
        except Exception:
            pass
            
        page.wait_for_load_state("domcontentloaded")

        if "login" in page.url.lower():
            err_elem = page.locator("#errormsg, .loginerrors, .alert-danger, #loginerrormessage")
            err_text = err_elem.first.inner_text().strip() if err_elem.count() > 0 else ""
            self.take_debug_screenshot(page, "error_login.png")
            detail = f" (Respuesta de Moodle: '{err_text}')" if err_text else ""
            raise ValueError(f"Credenciales inválidas o error de inicio de sesión en Moodle{detail}. Usuario intentado: '{masked_user}' (longitud {len(self.username)}), Contraseña longitud: {pass_len}. Revisa MOODLE_USER y MOODLE_PASS en el panel de Render.")

        context.storage_state(path=self.session_file)
        print("Sesión guardada exitosamente en session.json.")

    def ensure_authenticated(self, page: Page, context: BrowserContext) -> None:
        """Verifica si la sesión guardada en session.json es válida; si expiró, ejecuta el login de respaldo (fallback)."""
        if os.path.exists(self.session_file):
            print("🔑 Verificando cookie de sesión existente en session.json...")
            try:
                page.goto(f"{self.base_url}/my/", wait_until="domcontentloaded")
                if "login" not in page.url.lower():
                    print("⚡ Sesión activa reutilizada con éxito desde session.json. (Omitiendo formulario de login).")
                    return
                print("⚠️ La cookie de sesión guardada en session.json expiró. Ejecutando inicio de sesión de respaldo...")
            except Exception as e:
                print(f"Aviso al verificar cookie de sesión: {e}")

        # Fallback: Login completo si la cookie no existe o expiró
        self.login_and_save_session(page, context)

    def navigate_and_find_section(self, page: Page, course_id: str, categoria_nombre: str) -> int:
        """
        Navega al curso, activa 'Modo de edición', busca la pestaña/sección coincidente
        (ej. 'Recursos', 'Eventos', 'Interns & Job Offers') y retorna el índice de la sección.
        """
        print(f"Navegando a la vista principal del Curso {course_id}...")
        page.goto(f"{self.base_url}/course/view.php?id={course_id}", timeout=20000, wait_until="domcontentloaded")

        # 1. Activar 'Modo de edición' si no está activo
        try:
            edit_switch = page.locator('input[name="setmode"], .editmode-switch input')
            if edit_switch.count() > 0 and not edit_switch.first.is_checked():
                print("Activando 'Modo de edición'...")
                # Activar la casilla marcándola directamente en lugar de click() para evitar destruir el contexto de navegación
                try:
                    edit_switch.first.check(force=True)
                except Exception:
                    edit_switch.first.click()
                print("Modo de edición activado correctamente.")
        except Exception as e:
            print(f"Aviso al activar Modo de edición: {e}")

        self.take_debug_screenshot(page, f"curso_{course_id}_pestanas.png")

        # 2. Buscar la pestaña/sección correspondiente en la interfaz
        section_index = 0
        section_found = False

        print(f"Buscando la sección '{categoria_nombre}' en las pestañas del curso...")

        target_tab = page.locator('.nav-tabs a, .nav-link, ul.sections a, div.sectionname a, a[role="tab"]').filter(has_text=categoria_nombre)

        if target_tab.count() > 0:
            # Buscar atributo href o data-section / data-sectionid
            for t_idx in range(target_tab.count()):
                t_elem = target_tab.nth(t_idx)
                href = t_elem.get_attribute("href") or ""
                sec_attr = t_elem.get_attribute("data-section") or t_elem.get_attribute("data-sectionid") or ""
                
                match = re.search(r'section[=\-]?(\d+)', href) or re.search(r'^(\d+)$', sec_attr)
                if match:
                    section_index = int(match.group(1))
                    section_found = True
                    print(f"Índice de sección detectado vía atributo: {section_index}")
                    break

        if not section_found:
            print(f"Buscando sección '{categoria_nombre}' por análisis dinámico de pestañas del formato Onetopic...")
            section_info = page.evaluate("""
                (catName) => {
                    // Pestañas del formato por temas/pestañas de Moodle (Onetopic format)
                    const tabElements = document.querySelectorAll('ul.nav-tabs > li, .tabtree > ul > li, .course-content ul.sections > li');
                    for (let i = 0; i < tabElements.length; i++) {
                        const el = tabElements[i];
                        const text = el.innerText.trim();
                        if (text.toLowerCase().includes(catName.toLowerCase())) {
                            // Intentar obtener de enlace interno
                            const a = el.querySelector('a');
                            if (a && a.href) {
                                const m = a.href.match(/section[=\\-]?(\\d+)/);
                                if (m) return parseInt(m[1]);
                            }
                            // Retornar posición del tab (1-indexed en Moodle)
                            return i;
                        }
                    }
                    return null;
                }
            """, categoria_nombre)

            if section_info is not None:
                section_index = section_info
                section_found = True
                print(f"Sección '{categoria_nombre}' identificada dinámicamente en posición: {section_index}")

        return section_index

    def fill_tinymce_description(self, page: Page, html_content: str) -> None:
        """
        Espera a que el editor TinyMCE / Atto de Moodle cargue completamente e inyecta
        el contenido HTML de forma garantizada vía la API JS de TinyMCE e Iframe.
        """
        print("Esperando la inicialización del editor de Descripción (TinyMCE / Atto)...")
        try:
            page.locator('#id_introeditor_editable, iframe[id*="id_introeditor"], #id_introeditor').first.wait_for(state="attached", timeout=5000)
        except Exception:
            pass

        try:
            # 1. Inyección directa utilizando la API global de TinyMCE
            success = page.evaluate("""
                (content) => {
                    let set = false;
                    try {
                        if (window.tinyMCE && window.tinyMCE.get('id_introeditor')) {
                            window.tinyMCE.get('id_introeditor').setContent(content);
                            set = true;
                        } else if (window.tinymce && window.tinymce.get('id_introeditor')) {
                            window.tinymce.get('id_introeditor').setContent(content);
                            set = true;
                        } else if (window.tinyMCE && window.tinyMCE.activeEditor) {
                            window.tinyMCE.activeEditor.setContent(content);
                            set = true;
                        }
                    } catch(e) {}

                    if (!set) {
                        const el = document.querySelector('#id_introeditor_editable, [contenteditable="true"]');
                        if (el) {
                            el.innerHTML = content;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            set = true;
                        }
                    }

                    // Sincronizar campo textarea oculto si existe
                    const textarea = document.querySelector('#id_introeditor');
                    if (textarea) {
                        textarea.value = content;
                    }

                    return set;
                }
            """, html_content)

            if success:
                print("✅ Descripción inyectada correctamente vía API TinyMCE/DOM.")
            else:
                # 2. Fallback si TinyMCE se renderiza dentro de un iframe
                iframe = page.frame_locator('iframe[id*="id_introeditor"], iframe[id*="tinymce"]')
                if iframe.count() > 0:
                    iframe.locator('body').fill(html_content)
                    print("✅ Descripción inyectada dentro del Iframe de TinyMCE.")
                else:
                    editor_editable = page.locator('#id_introeditor_editable, [contenteditable="true"]')
                    if editor_editable.count() > 0:
                        editor_editable.first.fill(html_content)
                        print("✅ Descripción inyectada vía contenedor contenteditable.")

        except Exception as e:
            print(f"Aviso al inyectar en TinyMCE: {e}")

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
        # Si seccion viene como 0, None o no está especificada, ignorarla para no forzar la sección 'General'
        # y permitir que navigate_and_find_section ubique la pestaña 'Recursos' u otra categoría real.
        section_index = item.get("seccion")
        if section_index is None or str(section_index).strip() == "0":
            section_index = self.navigate_and_find_section(page, course_id, categoria)

        print(f"Publicando recurso URL en Curso {course_id} | Sección '{categoria}' (id: {section_index})...")

        # 2. Navegar al formulario de creación 'Nueva URL'
        url_crear = (
            f"{self.base_url}/course/modedit.php?"
            f"add=url&type=&course={course_id}&section={section_index}&return=0"
        )
        page.goto(url_crear, timeout=20000, wait_until="domcontentloaded")

        if "login" in page.url.lower():
            print("⚠️ Moodle redirigió a login a mitad del proceso. Re-autenticando vía fallback...")
            self.login_and_save_session(page, context)
            page.goto(url_crear, wait_until="domcontentloaded")

        # 3. Llenar Nombre con selector robusto y fallback JS
        try:
            name_input = page.locator('input[name="name"], #id_name, input#id_name').first
            name_input.wait_for(state="attached", timeout=12000)
            name_input.fill(nombre)
            print(f"Campo Nombre completado: '{nombre}'")
        except Exception as e:
            try:
                page.evaluate("""
                    (val) => {
                        const el = document.querySelector('input[name="name"], #id_name');
                        if (el) {
                            el.value = val;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }
                """, nombre)
                print(f"Campo Nombre completado vía JS fallback: '{nombre}'")
            except Exception:
                self.take_debug_screenshot(page, f"error_nombre_curso_{course_id}")
                raise TimeoutError(
                    f"No se encontró el campo '#id_name' en Moodle (Página actual: '{page.title()}', URL: '{page.url}')."
                )

        # 4. Llenar URL externa con selector robusto y fallback JS
        try:
            url_input = page.locator('input[name="externalurl"], #id_externalurl, input#id_externalurl').first
            url_input.fill(url)
            print(f"Campo URL externa completado: '{url}'")
        except Exception:
            page.evaluate("""
                (val) => {
                    const el = document.querySelector('input[name="externalurl"], #id_externalurl');
                    if (el) {
                        el.value = val;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }
            """, url)
            print(f"Campo URL externa completado vía JS fallback: '{url}'")

        # 5. Llenar Descripción enriquecida esperando a TinyMCE
        if descripcion_html:
            self.fill_tinymce_description(page, descripcion_html)

        # 6. Marcar casilla 'Mostrar descripción en la página del curso'
        try:
            show_desc = page.locator("#id_showdescription")
            if show_desc.count() > 0 and not show_desc.is_checked():
                show_desc.check()
                print("Casilla 'Mostrar descripción en la página del curso' activada.")
        except Exception as e:
            print(f"Aviso al activar casilla descripción: {e}")

        self.take_debug_screenshot(page, f"formulario_completado_curso_{course_id}.png")

        print("Guardando cambios en Moodle...")
        page.click("#id_submitbutton2")
        page.wait_for_load_state("domcontentloaded")
        print(f"✅ Recurso '{nombre}' publicado con éxito en la sección '{categoria}' del curso {course_id}.")
        self.take_debug_screenshot(page, f"curso_{course_id}_publicado.png")

    def set_moodle_date_fields(self, page: Page, prefix: str, target_dt: datetime.datetime) -> None:
        """
        Configura los campos de fecha y hora en el formulario de Moodle para Disponibilidad.
        prefix: 'allowsubmissionsfromdate', 'duedate', 'gradingduedate'
        """
        SPANISH_MONTHS = {
            1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
            5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
            9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
        }

        try:
            chk = page.locator(f"#id_{prefix}_enabled")
            if chk.count() > 0 and not chk.is_checked():
                chk.check()
                print(f"Casilla de habilitación de fecha '{prefix}' marcada.")

            day_str = str(target_dt.day)
            day_select = page.locator(f"#id_{prefix}_day")
            if day_select.count() > 0:
                try:
                    day_select.select_option(value=day_str)
                except Exception:
                    day_select.select_option(label=day_str)

            month_val = str(target_dt.month)
            month_label = SPANISH_MONTHS.get(target_dt.month, "")
            month_select = page.locator(f"#id_{prefix}_month")
            if month_select.count() > 0:
                try:
                    month_select.select_option(value=month_val)
                except Exception:
                    try:
                        month_select.select_option(label=month_label)
                    except Exception:
                        pass

            year_str = str(target_dt.year)
            year_select = page.locator(f"#id_{prefix}_year")
            if year_select.count() > 0:
                try:
                    year_select.select_option(value=year_str)
                except Exception:
                    year_select.select_option(label=year_str)

            hour_str = f"{target_dt.hour:02d}"
            hour_select = page.locator(f"#id_{prefix}_hour")
            if hour_select.count() > 0:
                try:
                    hour_select.select_option(value=str(target_dt.hour))
                except Exception:
                    hour_select.select_option(label=hour_str)

            minute_str = f"{(target_dt.minute // 5) * 5:02d}"
            minute_select = page.locator(f"#id_{prefix}_minute")
            if minute_select.count() > 0:
                try:
                    minute_select.select_option(value=str((target_dt.minute // 5) * 5))
                except Exception:
                    try:
                        minute_select.select_option(value=str(target_dt.minute))
                    except Exception:
                        minute_select.select_option(label=minute_str)

            print(f"📅 Fecha '{prefix}' configurada: {target_dt.strftime('%d/%m/%Y %H:%M')}")
        except Exception as e:
            print(f"Aviso al configurar campos de fecha '{prefix}': {e}")

    def publish_assignment(
        self, page: Page, item: Dict[str, Any], course_id: str
    ) -> None:
        """
        Crea un módulo de Tarea (assign) en la sección correspondiente del curso en Moodle.
        Configura Disponibilidad con 15 días límite a partir de hoy.
        """
        categoria = item.get("categoria_moodle") or "Tareas"
        nombre = item.get("nombre") or item.get("titulo", "Nueva Tarea")
        descripcion_html = item.get("descripcion_html") or item.get("contenido_html", "")
        dias_entrega = item.get("dias_entrega", 15)

        section_index = item.get("seccion")
        if section_index is None or str(section_index).strip() == "0":
            section_index = self.navigate_and_find_section(page, course_id, categoria)

        print(f"Publicando Tarea (assign) en Curso {course_id} | Sección '{categoria}' (id: {section_index})...")

        url_crear = (
            f"{self.base_url}/course/modedit.php?"
            f"add=assign&type=&course={course_id}&section={section_index}&return=0"
        )
        page.goto(url_crear)
        page.wait_for_load_state("domcontentloaded")

        if "login" in page.url.lower():
            print("⚠️ Moodle redirigió a login a mitad del proceso. Re-autenticando vía fallback...")
            self.login_and_save_session(page, context)
            page.goto(url_crear, wait_until="domcontentloaded")

        try:
            page.wait_for_selector("#id_name", timeout=12000)
            page.fill("#id_name", nombre)
            print(f"Campo Nombre de Tarea completado: '{nombre}'")
        except Exception as e:
            self.take_debug_screenshot(page, f"error_nombre_tarea_curso_{course_id}")
            raise TimeoutError(
                f"No se encontró el campo '#id_name' en Moodle Tarea (Página actual: '{page.title()}', URL: '{page.url}')."
            )

        if descripcion_html:
            self.fill_tinymce_description(page, descripcion_html)

        try:
            show_desc = page.locator("#id_showdescription")
            if show_desc.count() > 0 and not show_desc.is_checked():
                show_desc.check()
                print("Casilla 'Mostrar descripción en la página del curso' activada.")
        except Exception as e:
            print(f"Aviso al activar casilla descripción: {e}")

        now = datetime.datetime.now()
        due_date = now + datetime.timedelta(days=dias_entrega)
        grading_date = now + datetime.timedelta(days=dias_entrega + 5)

        self.set_moodle_date_fields(page, "allowsubmissionsfromdate", now)
        self.set_moodle_date_fields(page, "duedate", due_date)
        self.set_moodle_date_fields(page, "gradingduedate", grading_date)

        self.take_debug_screenshot(page, f"formulario_tarea_completado_curso_{course_id}.png")

        print("Guardando cambios de la Tarea en Moodle...")
        page.click("#id_submitbutton2")
        page.wait_for_load_state("domcontentloaded")
        print(f"✅ Tarea '{nombre}' creada con éxito con entrega a {dias_entrega} días en la sección '{categoria}' del curso {course_id}.")
        self.take_debug_screenshot(page, f"curso_{course_id}_tarea_publicada.png")

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

        self.fill_tinymce_description(page, mensaje)

        page.click("#id_submitbutton")
        page.wait_for_load_state("domcontentloaded")
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
        """Intenta lanzar Chromium con banderas optimizadas de memoria para entornos con 512MB RAM."""
        launch_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--no-zygote",
                        "--disable-extensions",
            "--disable-component-extensions-with-background-pages",
            "--disable-default-apps",
            "--mute-audio",
            "--no-first-run",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            '--js-flags="--max-old-space-size=128"',
        ]
        try:
            return p.chromium.launch(headless=True, args=launch_args)
        except Exception as e:
            if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
                print("Binarios de Chromium no encontrados. Instalando automáticamente...")
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
                return p.chromium.launch(headless=True, args=launch_args)
            raise e


    def publish_item(self, item: Dict[str, Any], course_id: Any = None, log_cb: Optional[Callable[[str, str], None]] = None) -> List[str]:
        """
        Publica un ítem en uno o varios cursos de manera secuencial (uno tras otro).
        """
        courses = self.resolve_target_courses(course_id or item.get("course_id") or item.get("courses"))
        published_courses = []

        self._log(f"🚀 Iniciando proceso de publicación en Moodle para {len(courses)} curso(s)...", "info", log_cb)

        with sync_playwright() as p:
            browser = self.launch_browser_safely(p)

            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            if os.path.exists(self.session_file):
                context = browser.new_context(storage_state=self.session_file, user_agent=ua)
            else:
                context = browser.new_context(user_agent=ua)

            page = context.new_page()
            # Desactivado bloqueo agresivo para evitar romper librerías o eventos de navegación en Moodle SEA Acatlán
            # page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_())

            try:
                self._log("🔑 Autenticando en Moodle SEA Acatlán...", "info", log_cb)
                self.ensure_authenticated(page, context)
                self._log("✅ Autenticación completada.", "success", log_cb)

                tipo = item.get("tipo", "recurso_url")
                categoria = item.get("categoria_moodle") or item.get("categoria", "")
                if categoria == "Tareas" or tipo == "tarea_assign":
                    tipo = "tarea_assign"

                failed_courses = []
                for cid in courses:
                    self._log(f"📌 Procesando Curso ID: {cid} | Verificando sección y formulario de creación...", "info", log_cb)
                    try:
                        if tipo == "tarea_assign":
                            self._log(f"📝 Publicando Tarea en Curso {cid}...", "info", log_cb)
                            self.publish_assignment(page, item, course_id=cid)
                            published_courses.append(cid)
                        elif tipo == "recurso_url":
                            self._log(f"🔗 Publicando Recurso URL en Curso {cid}...", "info", log_cb)
                            self.publish_url_resource(page, item, course_id=cid)
                            published_courses.append(cid)
                        elif tipo == "anuncio_foro":
                            self._log(f"📢 Publicando Anuncio en Foro...", "info", log_cb)
                            self.publish_forum_announcement(page, item)
                            published_courses.append(cid)
                        else:
                            raise ValueError(f"Tipo de recurso desconocido: {tipo}")
                        self._log(f"✅ Éxito al publicar en el Curso ID: {cid}", "success", log_cb)
                    except Exception as err:
                        page_url = page.url if 'page' in locals() and page else 'N/A'
                        self._log(f"⚠️ Error al publicar en el Curso ID: {cid}: {err} | URL actual: '{page_url}'", "error", log_cb)
                        failed_courses.append({"course_id": cid, "error": str(err)})

                if published_courses:
                    self._log(f"🎉 Publicación completada con éxito en los cursos: {', '.join(published_courses)}", "success", log_cb)
                
                if failed_courses:
                    failed_ids = [f['course_id'] for f in failed_courses]
                    self._log(f"❌ La publicación falló en los siguientes cursos: {', '.join(failed_ids)}", "warn", log_cb)

                if not published_courses and failed_courses:
                    raise RuntimeError(f"No se pudo publicar el recurso en ningún curso. Detalle de fallas: {failed_courses}")

            except Exception as e:
                self._log(f"❌ Error crítico en el flujo de Moodle: {e}", "error", log_cb)
                raise e
            finally:
                browser.close()

        return published_courses

