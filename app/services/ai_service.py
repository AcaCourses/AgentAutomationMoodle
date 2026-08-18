import json
import re
import time
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

GEMINI_MODELS_POOL = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash-exp",
    "gemini-1.5-flash-8b"
]

HF_MODELS_POOL = [
    "Qwen/Qwen2.5-72B-Instruct",
    "meta-llama/Llama-3.3-70B-Instruct",
    "Qwen/Qwen2.5-Coder-32B-Instruct",
    "mistralai/Mistral-Nemo-Instruct-2407"
]

GENERAL_SYSTEM_PROMPT = """Eres un consultor académico y de carrera laboral para estudiantes de Matemáticas Aplicadas y Computación (MAC) e Ingeniería en FES Acatlán (UNAM).

REGLAS DE CLASIFICACIÓN DE CATEGORÍA EN MOODLE:
1. "Recursos": Si es un CURSO (ej: "Curso Santander English", "Curso de Python", "Aprende...", "Tutorial", "Libro", "Certificación", "Herramienta").
2. "Eventos": Si es un WEBINAR, conferencia, taller en vivo, showcase con fecha/hora o reunión virtual/presencial.
3. "Interns & Job Offers": ÚNICAMENTE si es una VACANTE LABORAL DIRECTA / OFERTA DE EMPLEO / CONTRATACIÓN DE PASANTE (ej. "Amazon SDE Intern", "Buscamos Desarrollador Backend").

FEW-SHOT EXAMPLES (EJEMPLOS DE REFERENCIA):

Ejemplo 1 (CURSO / FORMACIÓN -> RECURSOS):
Texto: "Curso Santander British Council English online 2026 - 10.000 plazas gratis para mejorar tu inglés."
Respuesta esperada:
{
  "empresa_detectada": "Santander",
  "categoria_moodle": "Recursos",
  "nombre": "📚 Curso Gratuito de Inglés Santander British Council 2026",
  "descripcion_html": "<h4>🎓 ¿De qué trata este recurso?</h4><p>Programa gratuito de capacitación en idioma inglés ofrecido por British Council y Santander Open Academy.</p><h4>💼 ¿Por qué las empresas lo solicitan?</h4><p>El inglés técnico es indispensable para trabajar en empresas multinacionales de tecnología.</p><h4>🚀 Habilidades clave para tu CV</h4><ul><li>Inglés técnico profesional</li><li>Comunicación efectiva</li></ul><h4>📌 Recomendación Académica</h4><p>Aprovecha esta convocatoria gratuita para fortalecer tu CV antes de egresar.</p>"
}

Ejemplo 2 (WEBINAR / SHOWCASE -> EVENTOS):
Texto: "IBM Z Student Ambassador Showcase on September 9. Join us for lightning talks on LinuxONE."
Respuesta esperada:
{
  "empresa_detectada": "IBM",
  "categoria_moodle": "Eventos",
  "nombre": "📅 Showcase Virtual: IBM Z Student Ambassador",
  "descripcion_html": "<h4>🎓 ¿De qué trata este recurso?</h4><p>Evento virtual donde embajadores estudiantiles muestran proyectos reales construidos sobre tecnología IBM Z.</p><h4>💼 ¿Por qué las empresas lo solicitan?</h4><p>Las instituciones bancarias y financieras globales operan sus sistemas críticos sobre mainframes IBM.</p><h4>🚀 Habilidades clave para tu CV</h4><ul><li>Conocimientos en mainframes e infraestructura empresarial</li></ul><h4>📌 Recomendación Académica</h4><p>Asiste a este evento para conocer cómo otros alumnos colaboran directamente con IBM.</p>"
}

Ejemplo 3 (VACANTE LABORAL / CONTRATACIÓN -> INTERNS & JOB OFFERS):
Texto: "Amazon is hiring Software Development Engineer (SDE) Interns 2026. Qualifications: C++, Java or Python."
Respuesta esperada:
{
  "empresa_detectada": "Amazon",
  "categoria_moodle": "Interns & Job Offers",
  "nombre": "💼 Vacante SDE Intern 2026 - Amazon",
  "descripcion_html": "<h4>💼 Detalles de la Vacante / Convocatoria (Amazon)</h4><p>Oportunidad de pasantía laboral a tiempo completo para estudiantes de computación en Amazon.</p><h4>❓ Preguntas de Autoevaluación (¿Encajas con el perfil?)</h4><ul><li><b>¿Dominas Java, Python o C++?</b> Evalúa tu nivel práctico de programación.</li></ul><h4>🗺️ Roadmap de Estudio Exprès (¿Qué te falta aprender?)</h4><ul><li><b>Paso 1:</b> Repasa estructuras de datos y algoritmos.</li></ul><h4>📌 Recomendación del Profesor</h4><p>Aplica hoy mismo a esta vacante en Amazon.</p>"
}

Responde ÚNICAMENTE un JSON válido con la estructura del ejemplo.
"""

JOB_OFFER_SYSTEM_PROMPT = """Eres un mentor de reclutamiento técnico para estudiantes universitarios de Matemáticas Aplicadas y Computación (MAC) e Ingeniería en FES Acatlán (UNAM).

Tu objetivo es analizar una Oferta de Empleo / Pasantía Laboral / Vacante (Job Post) y crear una publicación en Moodle orientada a la AUTOEVALUACIÓN Y ROADMAP DE APRENDIZAJE del estudiante.

REGLAS DE CLASIFICACIÓN:
- "categoria_moodle": "Interns & Job Offers"

FEW-SHOT EXAMPLE:
Texto: "We are hiring Software Development Engineer Interns at Amazon. Requirements: Data structures, C++, Python or Java."
Respuesta esperada:
{
  "empresa_detectada": "Amazon",
  "categoria_moodle": "Interns & Job Offers",
  "nombre": "💼 Vacante SDE Intern 2026 - Amazon",
  "descripcion_html": "<h4>💼 Detalles de la Vacante / Convocatoria (Amazon)</h4><p>Puesto de pasantía técnica para desarrollo de software en la nube de Amazon.</p><h4>❓ Preguntas de Autoevaluación (¿Encajas con el perfil?)</h4><ul><li><b>¿Dominas lenguajes como Python, Java o C++?</b> Evalúa tus conocimientos en POO.</li><li><b>¿Comprendes estructuras de datos clave?</b> Verifica si puedes implementar listas, árboles y grafos.</li></ul><h4>🗺️ Roadmap de Estudio Exprès (¿Qué te falta aprender?)</h4><ul><li><b>Paso 1 - Algoritmos:</b> Resuelve problemas de complejidad algorítmica.</li><li><b>Paso 2 - Herramientas:</b> Practica con Git, Docker y servicios AWS.</li></ul><h4>📌 Recomendación del Profesor</h4><p>No dudes en enviar tu solicitud a Amazon para ganar valiosa experiencia en entrevistas técnicas.</p>"
}

Responde ÚNICAMENTE un JSON válido con esa estructura exacta.
"""


class AIService:
    def __init__(self):
        self.gemini_key = config.GEMINI_API_KEY
        self.hf_token = config.HF_TOKEN
        self.last_gemini_call = 0.0

    def enforce_gemini_rate_limit(self):
        """Pausa estratégica de 4.5 segundos para no exceder jamás el límite estricto de 15 RPM en Gemini."""
        now = time.time()
        elapsed = now - self.last_gemini_call
        if elapsed < 4.5:
            sleep_time = 4.5 - elapsed
            print(f"⏱️ Guardián de Rate Limit Gemini: Pausa preventiva de {sleep_time:.2f}s...")
            time.sleep(sleep_time)
        self.last_gemini_call = time.time()

    def call_gemini_api(self, system_prompt: str, user_prompt: str) -> Optional[Dict[str, Any]]:
        """Llama a la API de Google AI Studio Gemini con garantía de JSON estructurado y control estricto de cuota."""
        if not self.gemini_key or self.gemini_key == "tu_gemini_api_key_aqui":
            return None

        self.enforce_gemini_rate_limit()

        for model_name in GEMINI_MODELS_POOL:
            try:
                print(f"🌟 Solicitando enriquecimiento a Google AI Studio: '{model_name}'...")
                endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_key}"
                
                payload = {
                    "system_instruction": {
                        "parts": [{"text": system_prompt}]
                    },
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": user_prompt}]
                        }
                    ],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0.2,
                        "maxOutputTokens": 1100
                    }
                }

                with httpx.Client(timeout=15.0) as client:
                    response = client.post(endpoint, json=payload)
                    if response.status_code == 200:
                        res_data = response.json()
                        candidates = res_data.get("candidates", [])
                        if candidates:
                            raw_text = candidates[0]["content"]["parts"][0]["text"]
                            parsed = json.loads(raw_text, strict=False)
                            print(f"✅ Respuesta exitosa de Google AI Studio Gemini ('{model_name}').")
                            return parsed
                    elif response.status_code == 429:
                        print(f"⚠️ Rate limit 429 alcanzado en Gemini ('{model_name}'). Probando siguiente modelo...")
                    else:
                        print(f"Aviso en Gemini ('{model_name}'): HTTP {response.status_code} - {response.text[:150]}")
            except Exception as e:
                print(f"Aviso al consultar Google AI Studio ({model_name}): {e}")

        return None

    def parse_linkedin_iframe(self, linkedin_url: Optional[str]) -> Optional[str]:
        """Transforma una URL de publicación de LinkedIn en un iframe incrustado oficial."""
        if not linkedin_url or linkedin_url.strip().lower() in ["string", "null", "none", ""]:
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
        """Inyecta el iframe de LinkedIn o el logo Base64 de la empresa."""
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
        """Motor de enriquecimiento sintético local."""
        texto_lower = texto.lower()
        empresa_name = logo_info.get("nombre_empresa", "Empresa Tecnológica")

        # Criterio estricto de clasificación en fallback local
        is_course = any(w in texto_lower for w in ["curso", "course", "aprender", "aprender inglés", "idiomas", "beca de estudio", "tutorial", "capacitación"])
        is_event = any(w in texto_lower for w in ["webinar", "conferencia", "taller", "presencial", "en vivo", "showcase", "hackathon"])
        is_job = any(w in texto_lower for w in ["we are hiring", "job description", "vacante", "empleo", "contratando", "job offer", "sde intern", "puesto de trabajo"]) and not is_course

        if is_job:
            categoria = "Interns & Job Offers"
            nombre = f"💼 {empresa_name}: Vacante Laboral"
            base_html = (
                f"<h4>💼 Detalles de la Vacante / Convocatoria ({empresa_name})</h4><p>{texto}</p>"
                f"<h4>❓ Preguntas de Autoevaluación (¿Encajas con el perfil?)</h4>"
                f"<ul><li><b>¿Dominas los lenguajes principales?</b> Evalúa tus conocimientos prácticos.</li>"
                f"<li><b>¿Tienes proyectos en GitHub?</b> Verifica tus repositorios clave.</li></ul>"
                f"<h4>🗺️ Roadmap de Estudio Exprès (¿Qué te falta aprender?)</h4>"
                f"<ul><li><b>Paso 1:</b> Refuerza el lenguaje de programación principal.</li>"
                f"<li><b>Paso 2:</b> Practica con Git, Docker y bases de datos.</li></ul>"
                f"<h4>📌 Recomendación del Profesor</h4>"
                f"<p>¡No tengas miedo de postularte a {empresa_name}! Ganarás valiosa experiencia laboral.</p>"
            )
        elif is_event:
            categoria = "Eventos"
            lineas = [l.strip() for l in texto.split("\n") if l.strip()]
            titulo_clean = re.sub(r'^[^\w]+', '', lineas[0]) if lineas else texto[:40]
            nombre = f"📅 {titulo_clean[:55]}"
            base_html = (
                f"<h4>🎓 ¿De qué trata este recurso?</h4><p>{texto}</p>"
                f"<h4>💼 ¿Por qué {empresa_name} lo ofrece?</h4><p>Espacio de interacción directa con líderes de la industria.</p>"
                f"<h4>📌 Recomendación del Profesor</h4><p>Asiste a este evento para enriquecer tu aprendizaje.</p>"
            )
        else:
            categoria = "Recursos"
            lineas = [l.strip() for l in texto.split("\n") if l.strip()]
            titulo_clean = re.sub(r'^[^\w]+', '', lineas[0]) if lineas else texto[:40]
            nombre = f"📚 {titulo_clean[:55]}"
            base_html = (
                f"<h4>🎓 ¿De qué trata este recurso?</h4><p>{texto}</p>"
                f"<h4>💼 ¿Por me beneficia como estudiante?</h4><p>Fortalece tus habilidades técnicas con contenido oficial de {empresa_name}.</p>"
                f"<h4>📌 Recomendación del Profesor</h4><p>Excelente recurso para profundizar en tu carrera.</p>"
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
        """
        Jerarquía de Ejecución con Few-Shot Prompts y Criterio Estricto:
        1. 🥇 Google AI Studio Gemini API (gemini-1.5-flash / gemini-1.5-pro / gemini-2.0-flash-exp)
        2. 🥈 Hugging Face Pool (Qwen 72B / Llama 70B / Qwen Coder 32B / Mistral Nemo)
        3. 🥉 Motor Sintético Local
        """
        logo_info = self.resolve_company_logo(empresa_input, url, texto)
        empresa_name = logo_info["nombre_empresa"]

        research = self.perform_web_research(texto[:60], empresa_name)
        research_str = "\n".join([f"- {r['title']}: {r['snippet']}" for r in research])

        texto_lower = texto.lower()
        is_course = any(w in texto_lower for w in ["curso", "course", "aprender", "aprender inglés", "idiomas", "beca de estudio", "tutorial", "capacitación"])
        is_job_post = (
            any(w in texto_lower for w in [
                "we are hiring", "job description", "vacante de empleo",
                "oferta de empleo", "hiring software", "job vacancy",
                "sde intern", "puesto de trabajo", "postúlate a la vacante"
            ]) and not is_course
        )

        active_system_prompt = JOB_OFFER_SYSTEM_PROMPT if is_job_post else GENERAL_SYSTEM_PROMPT
        if is_job_post:
            print("💼 Detectada Oferta de Empleo / Job Post. Utilizando Prompt Especializado de Autoevaluación y Roadmap.")

        user_prompt = (
            f"Empresa Convocante: {empresa_name}\n"
            f"Publicación de origen:\n\"\"\"{texto}\"\"\"\nEnlace de Registro / Postulación: {url}\n\n"
            f"Datos de Investigación Web sobre {empresa_name} y Mercado:\n{research_str}"
        )

        # 1. 🥇 PRIORIDAD 1: Google AI Studio Gemini API
        gemini_res = self.call_gemini_api(active_system_prompt, user_prompt)
        if gemini_res:
            gemini_res["url"] = url
            if is_job_post:
                gemini_res["categoria_moodle"] = "Interns & Job Offers"
            elif is_course and gemini_res.get("categoria_moodle") == "Interns & Job Offers":
                gemini_res["categoria_moodle"] = "Recursos"

            gemini_res["descripcion_html"] = self.attach_header_to_html(
                gemini_res.get("descripcion_html", ""), logo_info, linkedin_url
            )
            gemini_res["empresa"] = empresa_name
            return gemini_res

        # 2. 🥈 PRIORIDAD 2: Hugging Face Inference API
        if self.hf_token and self.hf_token != "hf_tu_token_aqui":
            for model_name in HF_MODELS_POOL:
                try:
                    print(f"🤖 Solicitando enriquecimiento a Hugging Face: '{model_name}'...")
                    client = InferenceClient(model=model_name, token=self.hf_token)
                    messages = [
                        {"role": "system", "content": active_system_prompt},
                        {"role": "user", "content": user_prompt},
                    ]
                    res = client.chat_completion(messages=messages, max_tokens=1100, temperature=0.2)
                    raw = res.choices[0].message.content.strip()

                    if "```" in raw:
                        parts = raw.split("```")
                        for p in parts:
                            p_str = p.strip()
                            if p_str.startswith("json"):
                                p_str = p_str[4:].strip()
                            if p_str.startswith("{") and p_str.endswith("}"):
                                raw = p_str
                                break

                    try:
                        data = json.loads(raw, strict=False)
                    except Exception:
                        cleaned_raw = re.sub(r'[\r\n]+', r'\\n', raw)
                        data = json.loads(cleaned_raw, strict=False)

                    data["url"] = url
                    if is_job_post:
                        data["categoria_moodle"] = "Interns & Job Offers"
                    elif is_course and data.get("categoria_moodle") == "Interns & Job Offers":
                        data["categoria_moodle"] = "Recursos"

                    data["descripcion_html"] = self.attach_header_to_html(
                        data.get("descripcion_html", ""), logo_info, linkedin_url
                    )
                    data["empresa"] = empresa_name
                    print(f"✅ Enriquecimiento exitoso con modelo Hugging Face '{model_name}'.")
                    return data
                except Exception as e:
                    print(f"Aviso con modelo HF '{model_name}': {e}. Probando siguiente...")

        # 3. 🥉 PRIORIDAD 3: Motor Sintético Local
        print("💡 Utilizando Motor Sintético Local de Respaldo.")
        return self._fallback_categorize_and_enrich(texto, url, research, logo_info, linkedin_url)
