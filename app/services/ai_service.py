import json
import re
import base64
import httpx
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
from huggingface_hub import InferenceClient
from ddgs import DDGS
from app.config import config

# Mapas de dominios conocidos para logos corporativos HD
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

SYSTEM_PROMPT = """Eres un consultor académico y de carrera laboral para estudiantes de Matemáticas Aplicadas y Computación (MAC) e Ingeniería en FES Acatlán (UNAM).

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

Responde ÚNICAMENTE un JSON válido con esta estructura exacta:
{
  "empresa_detectada": "IBM",
  "categoria_moodle": "Recursos",
  "nombre": "🎓 Título Atractivo y Destacado",
  "descripcion_html": "<h4>🎓 ¿De qué trata este recurso?</h4><p>...</p><h4>💼 ¿Por qué las empresas lo solicitan?</h4><p>...</p><h4>🚀 Habilidades clave para tu CV</h4><ul><li>...</li></ul><h4>📌 Recomendación Académica</h4><p>...</p>"
}
"""


class AIService:
    def __init__(self):
        self.hf_token = config.HF_TOKEN

    def fetch_image_as_base64(self, url: str) -> Optional[str]:
        """Descarga una imagen de internet y la convierte a una Data URI en Base64 garantizada para Moodle."""
        try:
            with httpx.Client(timeout=5.0, follow_redirects=True) as client:
                res = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if res.status_code == 200 and len(res.content) > 100:
                    content_type = res.headers.get("content-type", "image/png").split(";")[0]
                    b64_str = base64.b64encode(res.content).decode("utf-8")
                    return f"data:{content_type};base64,{b64_str}"
        except Exception as e:
            print(f"Aviso al descargar logo para Base64 ({url}): {e}")
        return None

    def generate_svg_logo_base64(self, empresa_name: str) -> str:
        """Genera un badge en formato SVG Base64 de alta definición si no se puede descargar el logo externo."""
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
        """
        Resuelve deterministamente el logo oficial de la empresa y lo convierte a Base64
        para evitar bloqueos de seguridad XSS/CORS en Moodle.
        """
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

        # Intentar obtener Base64 desde dominios oficiales
        print(f"🏢 Empresa identificada: '{target_name}' (Dominio: {domain})")
        logo_urls_to_try = [
            f"https://logo.clearbit.com/{domain}",
            f"https://www.google.com/s2/favicons?domain={domain}&sz=128",
        ]

        base64_logo = None
        for img_url in logo_urls_to_try:
            base64_logo = self.fetch_image_as_base64(img_url)
            if base64_logo:
                print(f"✅ Logo convertido a Base64 Data URI exitosamente.")
                break

        if not base64_logo:
            print("💡 Generando SVG Base64 emblemático de la empresa...")
            base64_logo = self.generate_svg_logo_base64(target_name)

        return {"nombre_empresa": target_name, "domain": domain, "base64_logo": base64_logo}

    def attach_logo_header_to_html(self, html_content: str, logo_info: Dict[str, str]) -> str:
        """Incrustar la tarjeta con el logo oficial en Base64 al inicio de la descripción HTML."""
        base64_logo = logo_info.get("base64_logo")
        empresa_name = logo_info.get("nombre_empresa", "Empresa")

        if not base64_logo:
            return html_content

        header_card = (
            f'<div style="text-align: center; padding: 16px; margin-bottom: 20px; background: #ffffff; '
            f'border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">'
            f'  <img src="{base64_logo}" alt="Logo oficial {empresa_name}" '
            f'       style="max-height: 80px; max-width: 240px; object-fit: contain; display: inline-block; margin: 0 auto;" />'
            f'  <div style="font-size: 13px; color: #64748b; margin-top: 8px; font-weight: 600;">Contenido Oficial & Convocatoria de {empresa_name}</div>'
            f'</div>'
        )
        return header_card + html_content

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
        self, texto: str, url: str, research_data: List[Dict[str, str]], logo_info: Dict[str, str]
    ) -> Dict[str, Any]:
        """Motor de enriquecimiento sintético local utilizando el logo corporativo Base64."""
        texto_lower = texto.lower()
        empresa_name = logo_info.get("nombre_empresa", "Empresa Tecnológica")

        if any(w in texto_lower for w in ["webinar", "conferencia", "taller", "presencial", "en vivo", "call", "convocatoria", "solicítala", "fecha límite", "showcase"]):
            categoria = "Eventos"
            emoji = "📅"
        elif any(w in texto_lower for w in ["job", "intern", "vacante", "empleo", "hiring", "contratando", "postula", "becario", "pasantía", "oferta"]):
            categoria = "Interns & Job Offers"
            emoji = "💼"
        else:
            categoria = "Recursos"
            emoji = "📚"

        lineas = [l.strip() for l in texto.split("\n") if l.strip()]
        titulo_raw = lineas[0] if lineas else texto[:50]
        titulo_clean = re.sub(r'^[^\w]+', '', titulo_raw)
        if len(titulo_clean) > 60:
            titulo_clean = titulo_clean[:57] + "..."

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
            f"  <li><b>Acceso Oficial:</b> <a href='{url}' target='_blank'>Enlace a la convocatoria de {empresa_name}</a>.</li>"
            f"</ul>"
            f"<h4>📌 Recomendación del Profesor</h4>"
            f"<p>Este contenido de {empresa_name} ha sido seleccionado para complementar tu preparación académica en FES Acatlán. "
            f"Aprovechar estas convocatorias durante tu etapa universitaria potenciará tu perfil laboral al egresar.</p>"
        )

        final_html = self.attach_logo_header_to_html(base_html, logo_info)

        return {
            "categoria_moodle": categoria,
            "nombre": nombre,
            "descripcion_html": final_html,
            "url": url,
            "empresa": empresa_name,
        }

    def adapt_linkedin_post(self, texto: str, url: str, empresa_input: Optional[str] = None) -> Dict[str, Any]:
        """Transforma un post técnico en un recurso universitario enriquecido con IA, logo de empresa en Base64 e investigación web."""
        # 1. Resolver el logo de la empresa e inyectarlo en formato Base64 Data URI
        logo_info = self.resolve_company_logo(empresa_input, url, texto)
        empresa_name = logo_info["nombre_empresa"]

        # 2. Investigación web enfocada en la empresa y el contenido
        research = self.perform_web_research(texto[:60], empresa_name)
        research_str = "\n".join([f"- {r['title']}: {r['snippet']}" for r in research])

        if not self.hf_token:
            print("HF_TOKEN no configurado. Utilizando motor sintético con logo corporativo oficial en Base64.")
            return self._fallback_categorize_and_enrich(texto, url, research, logo_info)

        # 3. Probar pool de modelos de pesos abiertos en Hugging Face
        user_prompt = (
            f"Empresa Responsable: {empresa_name}\n"
            f"Publicación de origen:\n\"\"\"{texto}\"\"\"\nEnlace: {url}\n\n"
            f"Datos de Investigación Web sobre {empresa_name} y Mercado:\n{research_str}"
        )

        for model_name in HF_MODELS_POOL:
            try:
                print(f"🤖 Solicitando enriquecimiento a modelo HF: '{model_name}'...")
                client = InferenceClient(model=model_name, token=self.hf_token)
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ]
                res = client.chat_completion(messages=messages, max_tokens=1000, temperature=0.3)
                raw = res.choices[0].message.content.strip()

                if "```" in raw:
                    raw = raw.split("```json")[-1].split("```")[0].strip()

                data = json.loads(raw)
                data["url"] = url
                if "categoria_moodle" not in data:
                    data["categoria_moodle"] = "Recursos"

                # Inyectar la tarjeta con el logo Base64 al inicio del HTML retornado por la IA
                data["descripcion_html"] = self.attach_logo_header_to_html(
                    data.get("descripcion_html", ""), logo_info
                )
                data["empresa"] = empresa_name
                print(f"✅ Enriquecimiento y logo Base64 de {empresa_name} integrados exitosamente con modelo '{model_name}'.")
                return data
            except Exception as e:
                print(f"Aviso con modelo '{model_name}': {e}. Probando siguiente modelo...")

        # Fallback si los modelos HF están saturados
        return self._fallback_categorize_and_enrich(texto, url, research, logo_info)
