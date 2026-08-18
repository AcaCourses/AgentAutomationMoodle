import json
import re
import base64
import httpx
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
from huggingface_hub import InferenceClient
from ddgs import DDGS
from app.config import config

KNOWN_DOMAINS = {
    "ibm": "ibm.com",
    "santander": "santander.com",
    "santander open academy": "santanderopenacademy.com",
    "google": "google.com",
    "microsoft": "microsoft.com",
    "amazon": "amazon.com",
    "aws": "aws.amazon.com",
    "meta": "meta.com",
    "facebook": "meta.com",
    "linkedin": "linkedin.com",
    "airtable": "airtable.com",
    "oracle": "oracle.com",
    "cisco": "cisco.com",
    "nvidia": "nvidia.com",
    "intel": "intel.com",
    "github": "github.com",
}

HF_MODELS_POOL = [
    "Qwen/Qwen2.5-72B-Instruct",
    "meta-llama/Llama-3.3-70B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"
]

GENERAL_SYSTEM_PROMPT = """Eres un consultor académico y de carrera laboral para estudiantes de Matemáticas Aplicadas y Computación (MAC) e Ingeniería en FES Acatlán (UNAM).

Tu objetivo es tomar la información de un recurso/noticia y los hallazgos de INVESTIGACIÓN DE MERCADO, para generar una publicación sumamente enriquecida para Moodle.

Debes determinar:
1. "empresa_detectada": Identifica el nombre o marca de la empresa principal responsable (ej. "IBM", "Santander", "Microsoft", "Google", "Amazon", etc.).

2. "categoria_moodle": Clasifica en una de estas 3 opciones:
   - "Eventos" (Si es un webinar, taller, beca en vivo, convocatoria con fecha límite o conferencia)
   - "Interns & Job Offers" (Si es una vacante de empleo, pasantía o convocatoria laboral directa)
   - "Recursos" (Si es un curso, tutorial, artículo, repositorio o herramienta técnica)

3. "nombre": Un título irresistible, profesional y motivador (con emoji inicial, máximo 70 caracteres).

4. "descripcion_html": Estructura HTML rica y detallada que DEBE INCLUIR:
   - <h4>🎓 ¿De qué trata este recurso?</h4> <p>Resumen claro del contenido y sus características principales.</p>
   - <h4>💼 ¿Por qué las empresas y la industria lo solicitan?</h4> <p>Explicación respaldada por por qué esta empresa u otras gigantes tecnológicas buscan estas habilidades, impacto en salarios u oportunidades internacionales.</p>
   - <h4>🚀 Habilidades clave para tu CV</h4> <ul><li>Habilidad 1</li><li>Habilidad 2</li><li>Habilidad 3</li></ul>
   - <h4>📌 Recomendación Académica</h4> <p>Mensaje motivacional del profesor para los alumnos de MAC.</p>

Responde ÚNICAMENTE un JSON válido con esta estructura exacta.
"""

JOB_OFFER_SYSTEM_PROMPT = """Eres un mentor de reclutamiento técnico para estudiantes universitarios de Matemáticas Aplicadas y Computación (MAC) e Ingeniería en FES Acatlán (UNAM).

Tu objetivo es analizar una Oferta de Empleo / Pasantía / Vacante (Job Post) y crear una publicación en Moodle orientada a la AUTOEVALUACIÓN Y ROADMAP DE APRENDIZAJE del estudiante.

Debes determinar:
1. "empresa_detectada": Nombre de la empresa convocante (ej. "Amazon", "Google", "IBM", "Mercado Libre", etc.).

2. "categoria_moodle": "Interns & Job Offers"

3. "nombre": Título motivador y profesional con emoji (ej. "💼 Vacante Backend Developer - Amazon (Pasantía)").

4. "descripcion_html": Estructura HTML orientada a AUTOEVALUACIÓN Y ROADMAP que DEBE INCLUIR:
   - <h4>💼 Detalles de la Vacante / Convocatoria</h4> <p>Resumen del puesto, empresa y los requisitos principales que buscan en el candidato.</p>
   - <h4>❓ Preguntas de Autoevaluación (¿Encajas con el perfil?)</h4>
     <p>Responde mentalmente estas preguntas para medir si estás listo para postularte hoy:</p>
     <ul>
       <li><b>¿Dominas...?</b> [Pregunta sobre lenguaje o tecnología clave requerida]</li>
       <li><b>¿Tienes experiencia en...?</b> [Pregunta sobre arquitecturas, herramientas o bases de datos]</li>
       <li><b>¿Conoces...?</b> [Pregunta sobre metodologías, lógica de programación o inglés]</li>
     </ul>
   - <h4>🗺️ Roadmap de Estudio Exprès (¿Qué te falta aprender?)</h4>
     <p>Si no cumples con todos los requisitos aún, enfócate en estudiar estos temas clave para esta y futuras vacantes:</p>
     <ul>
       <li><b>Paso 1 - Fundamentos:</b> [Tema técnico principal a estudiar]</li>
       <li><b>Paso 2 - Herramientas Prácticas:</b> [Framework o herramienta técnica a practicar]</li>
       <li><b>Paso 3 - Proyectos / CV:</b> [Consejo para construir un proyecto de portafolio relevante]</li>
     </ul>
   - <h4>📌 Recomendación del Profesor</h4> <p>Mensaje motivacional para no tener miedo a postularse e intentar la vacante.</p>

Responde ÚNICAMENTE un JSON válido con esa estructura exacta.
"""


class AIService:
    def __init__(self):
        self.hf_token = config.HF_TOKEN

    def parse_linkedin_iframe(self, linkedin_url: Optional[str]) -> Optional[str]:
        """Transforma una URL de publicación de LinkedIn en un iframe incrustado oficial."""
        if not linkedin_url:
            return None

        if "<iframe" in linkedin_url.lower():
            match = re.search(r'src=["\']([^"\']+)["\']', linkedin_url)
            if match:
                src = match.group(1)
                return (
                    f'<div style="text-align: center; margin-bottom: 20px; display: flex; justify-content: center;">'
                    f'  <iframe src="{src}" height="550" width="100%" style="max-width: 504px; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.08);" frameborder="0" allowfullscreen="" title="Publicación integrada de LinkedIn"></iframe>'
                    f'</div>'
                )
            return linkedin_url

        urn_match = re.search(r'(urn:li:(?:activity|share):\d+)', linkedin_url)
        if urn_match:
            urn = urn_match.group(1)
            embed_src = f"https://www.linkedin.com/embed/feed/update/{urn}?collapsed=1"
            print(f"🔗 LinkedIn URN detectado: '{urn}' -> iframe embed generado.")
            return (
                f'<div style="text-align: center; margin-bottom: 20px; display: flex; justify-content: center;">'
                f'  <iframe src="{embed_src}" height="550" width="100%" style="max-width: 504px; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.08);" frameborder="0" allowfullscreen="" title="Publicación integrada de LinkedIn"></iframe>'
                f'</div>'
            )

        return None

    def fetch_image_as_base64(self, url: str) -> Optional[str]:
        """Descarga una imagen de internet y la convierte a Data URI en Base64."""
        try:
            with httpx.Client(timeout=5.0, follow_redirects=True) as client:
                res = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if res.status_code == 200 and len(res.content) > 100:
                    content_type = res.headers.get("content-type", "image/png").split(";")[0]
                    b64_str = base64.b64encode(res.content).decode("utf-8")
                    return f"data:{content_type};base64,{b64_str}"
        except Exception as e:
            print(f"Aviso al descargar logo Base64 ({url}): {e}")
        return None

    def generate_svg_logo_base64(self, empresa_name: str) -> str:
        """Genera un badge en formato SVG Base64."""
        clean_name = empresa_name.upper()[:25]
        svg_code = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="240" height="60" viewBox="0 0 240 60">'
            f'  <rect width="240" height="60" rx="10" fill="#0f172a"/>'
            f'  <text x="120" y="37" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="18" font-weight="bold" fill="#38bdf8" text-anchor="middle">{clean_name}</text>'
            f'</svg>'
        )
        b64_str = base64.b64encode(svg_code.encode("utf-8")).decode("utf-8")
        return f"data:image/svg+xml;base64,{b64_str}"

    def resolve_company_logo(self, empresa_input: Optional[str], url: str, texto: str) -> Dict[str, str]:
        """Resuelve el logo de la empresa y lo convierte a Base64."""
        target_name = (empresa_input or "").strip()
        domain = ""

        if "." in target_name and not " " in target_name:
            domain = target_name.lower()
            target_name = domain.split(".")[0].upper()
        elif target_name.lower() in KNOWN_DOMAINS:
            domain = KNOWN_DOMAINS[target_name.lower()]
        elif target_name:
            domain = target_name.lower().replace(" ", "") + ".com"
        else:
            parsed = urlparse(url)
            netloc = parsed.netloc.replace("www.", "")
            if netloc and "." in netloc:
                domain = netloc
                target_name = netloc.split(".")[0].capitalize()

        if not target_name:
            texto_lower = texto.lower()
            for key, dom in KNOWN_DOMAINS.items():
                if key in texto_lower:
                    target_name = key.upper()
                    domain = dom
                    break

        if not target_name:
            target_name = "Empresa Tecnológica"
            domain = "linkedin.com"

        print(f"🏢 Empresa identificada: '{target_name}' (Dominio: {domain})")
        logo_urls_to_try = [
            f"https://logo.clearbit.com/{domain}",
            f"https://www.google.com/s2/favicons?domain={domain}&sz=128",
        ]

        base64_logo = None
        for img_url in logo_urls_to_try:
            base64_logo = self.fetch_image_as_base64(img_url)
            if base64_logo:
                break

        if not base64_logo:
            base64_logo = self.generate_svg_logo_base64(target_name)

        return {"nombre_empresa": target_name, "domain": domain, "base64_logo": base64_logo}

    def attach_header_to_html(
        self, html_content: str, logo_info: Dict[str, str], linkedin_url: Optional[str] = None
    ) -> str:
        """
        Si existe linkedin_url, inyecta el iframe de la publicación de LinkedIn.
        Si no existe, inyecta la tarjeta con el logo de la empresa en Base64.
        """
        iframe_header = self.parse_linkedin_iframe(linkedin_url)
        if iframe_header:
            print("📌 Encabezado: Publicación de LinkedIn incrustada (Iframe).")
            return iframe_header + html_content

        base64_logo = logo_info.get("base64_logo")
        empresa_name = logo_info.get("nombre_empresa", "Empresa")

        if base64_logo:
            print(f"📌 Encabezado: Tarjeta de logo oficial de {empresa_name}.")
            logo_card = (
                f'<div style="text-align: center; padding: 16px; margin-bottom: 20px; background: #ffffff; '
                f'border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">'
                f'  <img src="{base64_logo}" alt="Logo oficial {empresa_name}" '
                f'       style="max-height: 80px; max-width: 240px; object-fit: contain; display: inline-block; margin: 0 auto;" />'
                f'  <div style="font-size: 13px; color: #64748b; margin-top: 8px; font-weight: 600;">Contenido Oficial & Convocatoria de {empresa_name}</div>'
                f'</div>'
            )
            return logo_card + html_content

        return html_content

    def perform_web_research(self, topic: str, empresa: str) -> List[Dict[str, str]]:
        """Realiza una búsqueda web concisa en tiempo real para obtener datos del mercado laboral."""
        results = []
        try:
            search_query = f"{empresa} {topic} importancia empresas empleo tecnología STEM"
            print(f"🔍 Investigando en la web: '{search_query[:70]}'...")
            with DDGS() as ddgs:
                ddg_res = list(ddgs.text(search_query, max_results=3))
                for item in ddg_res:
                    results.append({
                        "title": item.get("title", ""),
                        "snippet": item.get("body", "")
                    })
            print(f"✅ Investigación web completada ({len(results)} resultados obtenidos).")
        except Exception as e:
            print(f"Aviso en investigación web: {e}")
        return results

    def _fallback_categorize_and_enrich(
        self, texto: str, url: str, research_data: List[Dict[str, str]], logo_info: Dict[str, str], linkedin_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Motor de enriquecimiento sintético local con lógica diferenciada para Ofertas de Empleo vs Recursos/Eventos."""
        texto_lower = texto.lower()
        empresa_name = logo_info.get("nombre_empresa", "Empresa Tecnológica")

        is_job_post = any(w in texto_lower for w in ["job", "intern", "vacante", "empleo", "hiring", "contratando", "postula", "becario", "pasantía", "oferta", "reclutamiento"])

        lineas = [l.strip() for l in texto.split("\n") if l.strip()]
        titulo_raw = lineas[0] if lineas else texto[:50]
        titulo_clean = re.sub(r'^[^\w]+', '', titulo_raw)
        if len(titulo_clean) > 60:
            titulo_clean = titulo_clean[:57] + "..."

        if is_job_post:
            categoria = "Interns & Job Offers"
            nombre = f"💼 {empresa_name}: {titulo_clean}"

            base_html = (
                f"<h4>💼 Detalles de la Vacante / Convocatoria ({empresa_name})</h4>"
                f"<p>{texto}</p>"
                f"<h4>❓ Preguntas de Autoevaluación (¿Encajas con el perfil?)</h4>"
                f"<p>Antes de postularte, evalúa honestamente tu nivel actual respondiendo estas preguntas:</p>"
                f"<ul>"
                f"  <li><b>¿Dominas los lenguajes principales solicitados?</b> Evalúa tus conocimientos prácticos en programación orientada a objetos o estructuras de datos.</li>"
                f"  <li><b>¿Tienes proyectos en GitHub que respalden tus conocimientos?</b> Verifica si tus repositorios demuestran las tecnologías clave que busca {empresa_name}.</li>"
                f"  <li><b>¿Puedes comunicarte técnicamente en inglés?</b> Revisa tu capacidad para redactar documentación o explicar tu código en inglés.</li>"
                f"</ul>"
                f"<h4>🗺️ Roadmap de Estudio Exprès (¿Qué te falta aprender?)</h4>"
                f"<p>Si aún no cumples con el 100% de los requisitos, enfócate en fortalecer estos pilares clave:</p>"
                f"<ul>"
                f"  <li><b>Paso 1 - Fundamentos Técnicos:</b> Refuerza el lenguaje de programación principal y patrones de diseño.</li>"
                f"  <li><b>Paso 2 - Herramientas de la Industria:</b> Practica con Git, Docker, bases de datos SQL/NoSQL y APIs REST.</li>"
                f"  <li><b>Paso 3 - Proyecto de Portafolio:</b> Desarrolla una aplicación pequeña que resuelva un problema real usando la tecnología solicitada.</li>"
                f"</ul>"
                f"<h4>📌 Recomendación del Profesor</h4>"
                f"<p>¡No tengas miedo de postularte a {empresa_name}! Incluso si sientes que te falta aprender un tema, el proceso de entrevista te dará valiosa experiencia en la industria real.</p>"
            )
        else:
            if any(w in texto_lower for w in ["webinar", "conferencia", "taller", "presencial", "en vivo", "call", "convocatoria", "solicítala", "fecha límite", "showcase"]):
                categoria = "Eventos"
                emoji = "📅"
            else:
                categoria = "Recursos"
                emoji = "📚"

            nombre = f"{emoji} {titulo_clean}"

            mercado_info = ""
            if research_data:
                mercado_info = " ".join([r["snippet"] for r in research_data[:2]])
            else:
                mercado_info = (
                    f"Empresas e instituciones globales como {empresa_name} buscan activamente talento capacitado en estas herramientas clave, "
                    f"lo que incrementa significativamente la empleabilidad y el desarrollo profesional de los estudiantes."
                )

            base_html = (
                f"<h4>🎓 ¿De qué trata este recurso?</h4>"
                f"<p>{texto}</p>"
                f"<h4>💼 ¿Por qué {empresa_name} y la industria lo solicitan?</h4>"
                f"<p><b>Impacto en el mercado laboral:</b> {mercado_info}</p>"
                f"<h4>🚀 Habilidades clave para potenciar tu CV</h4>"
                f"<ul>"
                f"  <li><b>Competitividad Internacional:</b> Formación respaldada por la industria global.</li>"
                f"  <li><b>Perfil de Alto Valor:</b> Diferenciador clave para postulaciones laborales en {empresa_name} y tecnológicas.</li>"
                f"  <li><b>Registro / Acceso Oficial:</b> <a href='{url}' target='_blank'>Haz clic aquí para ingresar al registro directo</a>.</li>"
                f"</ul>"
                f"<h4>📌 Recomendación del Profesor</h4>"
                f"<p>Este contenido de {empresa_name} ha sido seleccionado para complementar tu preparación académica en FES Acatlán. "
                f"Aprovechar estas convocatorias durante tu etapa universitaria potenciará tu perfil laboral al egresar.</p>"
            )

        final_html = self.attach_header_to_html(base_html, logo_info, linkedin_url)

        return {
            "categoria_moodle": categoria,
            "nombre": nombre,
            "descripcion_html": final_html,
            "url": url,
            "empresa": empresa_name,
        }

    def adapt_linkedin_post(
        self, texto: str, url: str, empresa_input: Optional[str] = None, linkedin_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Transforma un post técnico en un recurso universitario enriquecido con IA, iframe/logo e investigación web."""
        logo_info = self.resolve_company_logo(empresa_input, url, texto)
        empresa_name = logo_info["nombre_empresa"]

        research = self.perform_web_research(texto[:60], empresa_name)
        research_str = "\n".join([f"- {r['title']}: {r['snippet']}" for r in research])

        # Determinar si el post corresponde a una oferta de empleo para seleccionar el System Prompt óptimo
        texto_lower = texto.lower()
        is_job_post = any(w in texto_lower for w in ["job", "intern", "vacante", "empleo", "hiring", "contratando", "postula", "becario", "pasantía", "oferta", "reclutamiento"])

        active_system_prompt = JOB_OFFER_SYSTEM_PROMPT if is_job_post else GENERAL_SYSTEM_PROMPT
        if is_job_post:
            print("💼 Detectada Oferta de Empleo / Job Post. Utilizando Prompt Especializado de Autoevaluación y Roadmap.")

        if not self.hf_token:
            print("HF_TOKEN no configurado. Utilizando motor sintético con plantilla adaptativa.")
            return self._fallback_categorize_and_enrich(texto, url, research, logo_info, linkedin_url)

        user_prompt = (
            f"Empresa Convocante: {empresa_name}\n"
            f"Publicación de origen:\n\"\"\"{texto}\"\"\"\nEnlace de Registro / Postulación: {url}\n\n"
            f"Datos de Investigación Web sobre {empresa_name} y Mercado:\n{research_str}"
        )

        for model_name in HF_MODELS_POOL:
            try:
                print(f"🤖 Solicitando enriquecimiento a modelo HF: '{model_name}'...")
                client = InferenceClient(model=model_name, token=self.hf_token)
                messages = [
                    {"role": "system", "content": active_system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
                res = client.chat_completion(messages=messages, max_tokens=1100, temperature=0.3)
                raw = res.choices[0].message.content.strip()

                if "```" in raw:
                    raw = raw.split("```json")[-1].split("```")[0].strip()

                data = json.loads(raw)
                data["url"] = url
                if is_job_post:
                    data["categoria_moodle"] = "Interns & Job Offers"

                data["descripcion_html"] = self.attach_header_to_html(
                    data.get("descripcion_html", ""), logo_info, linkedin_url
                )
                data["empresa"] = empresa_name
                print(f"✅ Enriquecimiento e incrustación integrados exitosamente con modelo '{model_name}'.")
                return data
            except Exception as e:
                print(f"Aviso con modelo '{model_name}': {e}. Probando siguiente modelo...")

        return self._fallback_categorize_and_enrich(texto, url, research, logo_info, linkedin_url)
