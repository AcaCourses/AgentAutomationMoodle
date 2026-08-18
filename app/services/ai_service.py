import json
import re
from typing import Dict, Any, List, Optional
from urllib.parse import quote, urlparse
from huggingface_hub import InferenceClient
from ddgs import DDGS
from app.config import config

# Modelos de pesos abiertos soportados en Hugging Face
HF_MODELS_POOL = [
    "Qwen/Qwen2.5-72B-Instruct",
    "meta-llama/Llama-3.3-70B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"
]

SYSTEM_PROMPT = """Eres un consultor académico y de carrera laboral para estudiantes de la Licenciatura en Matemáticas Aplicadas y Computación (MAC) e Ingeniería en FES Acatlán (UNAM).

Tu objetivo es tomar la información de un recurso/noticia y los hallazgos de INVESTIGACIÓN DE MERCADO Y BÚSQUEDA WEB, para generar una publicación sumamente enriquecida, persuasiva y de alto valor para Moodle.

Debes determinar:
1. "categoria_moodle": Clasifica en una de estas 3 opciones:
   - "Eventos" (Si es un webinar, taller, beca en vivo, convocatoria con fecha límite o conferencia)
   - "Interns & Job Offers" (Si es una vacante de empleo, pasantía o convocatoria laboral directa)
   - "Recursos" (Si es un curso, tutorial, artículo, repositorio o herramienta técnica)

2. "nombre": Un título irresistible, profesional y motivador (con emoji inicial, máximo 70 caracteres).

3. "descripcion_html": Estructura HTML rica y detallada que DEBE INCLUIR:
   - <h4>🎓 ¿De qué trata este recurso?</h4> <p>Resumen claro del contenido y sus características principales.</p>
   - <h4>💼 ¿Por qué las empresas y la industria lo solicitan?</h4> <p>Explicación detallada respaldada por la investigación web sobre por qué gigantes tecnológicos o empresas (ej. IBM, Amazon, Santander, Google, etc.) buscan estas habilidades, impacto en salarios u oportunidades internacionales.</p>
   - <h4>🚀 Habilidades clave para tu CV</h4> <ul><li>Habilidad 1</li><li>Habilidad 2</li><li>Habilidad 3</li></ul>
   - <h4>📌 Recomendación Académica</h4> <p>Mensaje motivacional del profesor indicando por qué ningún alumno de MAC debe dejarlo pasar.</p>

Responde ÚNICAMENTE un JSON válido con esta estructura exacta:
{
  "categoria_moodle": "Recursos",
  "nombre": "🎓 Título Atractivo y Destacado",
  "descripcion_html": "<h4>🎓 ¿De qué trata este recurso?</h4><p>...</p><h4>💼 ¿Por qué las empresas lo solicitan?</h4><p>...</p><h4>🚀 Habilidades clave para tu CV</h4><ul><li>...</li></ul><h4>📌 Recomendación Académica</h4><p>...</p>"
}
"""


class AIService:
    def __init__(self):
        self.hf_token = config.HF_TOKEN

    def extract_search_topic(self, texto: str, url: str) -> str:
        """Extrae un tema conciso de 3 a 5 palabras para búsquedas web e imágenes."""
        clean_text = re.sub(r'https?://\S+', '', texto).strip()
        first_line = [l.strip() for l in clean_text.split('\n') if l.strip()]
        topic_base = first_line[0] if first_line else clean_text[:40]
        words = [w for w in re.findall(r'\b[A-Za-z0-9áéíóúÁÉÍÓÚñÑ]{3,}\b', topic_base) if w.lower() not in ['para', 'sobre', 'desde', 'con', 'este', 'esta', 'como']]
        return " ".join(words[:5]) if words else "Tecnologia Computacion"

    def search_web_image(self, topic: str, url: str) -> Optional[str]:
        """Busca una imagen o logo relevante en la web o utiliza Clearbit/Pollinations de respaldo."""
        print(f"🖼️ Buscando imagen relevante en la web para '{topic}'...")
        try:
            with DDGS() as ddgs:
                img_res = list(ddgs.images(f"{topic} logo banner", max_results=3))
                for item in img_res:
                    img_url = item.get("image")
                    if img_url and (img_url.startswith("http://") or img_url.startswith("https://")):
                        print(f"✅ Imagen encontrada vía DuckDuckGo: {img_url}")
                        return img_url
        except Exception as e:
            print(f"Aviso en búsqueda de imagen DDG: {e}")

        # Fallback 1: Intentar extraer el dominio para Clearbit Logo API (ej. ibm.com, santander.com)
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.replace("www.", "")
            if domain and "." in domain:
                logo_url = f"https://logo.clearbit.com/{domain}"
                print(f"💡 Utilizando logo oficial del sitio: {logo_url}")
                return logo_url
        except Exception:
            pass

        # Fallback 2: Banner conceptual vía Pollinations AI
        safe_topic = quote(topic)
        pollinations_url = f"https://image.pollinations.ai/prompt/professional%20technology%20banner%20{safe_topic}?width=600&height=300&nologo=true"
        return pollinations_url

    def perform_web_research(self, topic: str) -> List[Dict[str, str]]:
        """Realiza una búsqueda web concisa en tiempo real para obtener datos reales del mercado laboral."""
        results = []
        try:
            search_query = f"{topic} importancia empresas empleo tecnologia"
            print(f"🔍 Investigando en la web: '{search_query}'...")
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

    def attach_image_to_html(self, html_content: str, image_url: Optional[str], topic: str) -> str:
        """Incrustar la imagen destacada centrada y con estilo en el encabezado de la descripción HTML."""
        if not image_url:
            return html_content

        image_header = (
            f'<div style="text-align: center; margin-bottom: 20px; padding: 10px; background: #f8f9fa; border-radius: 12px; border: 1px solid #e9ecef;">'
            f'  <img src="{image_url}" alt="{topic}" style="max-width: 100%; max-height: 240px; border-radius: 8px; object-fit: contain; box-shadow: 0 4px 10px rgba(0,0,0,0.12);" />'
            f'</div>'
        )
        return image_header + html_content

    def _fallback_categorize_and_enrich(
        self, texto: str, url: str, research_data: List[Dict[str, str]], image_url: Optional[str], topic: str
    ) -> Dict[str, Any]:
        """Motor de enriquecimiento avanzado local utilizando datos web reales e imagen de respaldo."""
        texto_lower = texto.lower()

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
                "Empresas e instituciones líderes en tecnología (como IBM, Amazon, Santander y Microsoft) "
                "buscan constantemente talento capacitado en estas herramientas clave, lo que incrementa significativamente "
                "la empleabilidad y las oportunidades profesionales para los estudiantes."
            )

        base_html = (
            f"<h4>🎓 ¿De qué trata este recurso?</h4>"
            f"<p>{texto}</p>"
            f"<h4>💼 ¿Por qué las empresas y la industria lo solicitan?</h4>"
            f"<p><b>Impacto en el mercado laboral:</b> {mercado_info}</p>"
            f"<h4>🚀 Habilidades clave para potenciar tu CV</h4>"
            f"<ul>"
            f"  <li><b>Competitividad Internacional:</b> Formación alineada a estándares globales de la industria tecnológica.</li>"
            f"  <li><b>Perfil de Alto Valor:</b> Diferenciador clave para postulaciones a pasantías, convocatorias y empleos.</li>"
            f"  <li><b>Acceso Oficial:</b> <a href='{url}' target='_blank'>Enlace al sitio oficial del recurso</a>.</li>"
            f"</ul>"
            f"<h4>📌 Recomendación del Profesor</h4>"
            f"<p>Este contenido ha sido seleccionado para complementar tu preparación académica en FES Acatlán. "
            f"Aprovechar estas convocatorias durante tu etapa universitaria potenciará tu perfil laboral al egresar.</p>"
        )

        final_html = self.attach_image_to_html(base_html, image_url, topic)

        return {
            "categoria_moodle": categoria,
            "nombre": nombre,
            "descripcion_html": final_html,
            "url": url,
        }

    def adapt_linkedin_post(self, texto: str, url: str) -> Dict[str, Any]:
        """Transforma un post técnico en un recurso universitario enriquecido con IA, Web Research e Imágenes."""
        # 1. Extraer tema limpio y realizar investigación web e imagen
        topic = self.extract_search_topic(texto, url)
        research = self.perform_web_research(topic)
        image_url = self.search_web_image(topic, url)

        research_str = "\n".join([f"- {r['title']}: {r['snippet']}" for r in research])

        if not self.hf_token:
            print("HF_TOKEN no configurado. Utilizando motor de investigación sintética con imágenes.")
            return self._fallback_categorize_and_enrich(texto, url, research, image_url, topic)

        # 2. Probar pool de modelos de pesos abiertos en Hugging Face
        user_prompt = (
            f"Publicación de origen:\n\"\"\"{texto}\"\"\"\nEnlace: {url}\n\n"
            f"Tema Clave: {topic}\n\n"
            f"Datos de Investigación Web sobre Demanda en la Industria:\n{research_str}"
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

                # Inyectar imagen al inicio del HTML retornado por el LLM
                data["descripcion_html"] = self.attach_image_to_html(
                    data.get("descripcion_html", ""), image_url, topic
                )
                print(f"✅ Enriquecimiento e imagen integrados exitosamente con modelo '{model_name}'.")
                return data
            except Exception as e:
                print(f"Aviso con modelo '{model_name}': {e}. Probando siguiente modelo...")

        # Fallback si todos los modelos HF están saturados
        return self._fallback_categorize_and_enrich(texto, url, research, image_url, topic)
