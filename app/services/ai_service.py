import json
import re
from typing import Dict, Any, List
from huggingface_hub import InferenceClient
from duckduckgo_search import DDGS
from app.config import config

# Modelos de pesas abiertos soportados en Hugging Face
HF_MODELS_POOL = [
    "Qwen/Qwen2.5-72B-Instruct",
    "meta-llama/Llama-3.3-70B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"
]

SYSTEM_PROMPT = """Eres un consultor académico y de carrera laboral para estudiantes de la Licenciatura en Matemáticas Aplicadas y Computación (MAC) e Ingeniería en FES Acatlán (UNAM).

Tu objetivo es tomar la información de un recurso/noticia y los hallazgos de INVESTIGACIÓN DE MERCADO WEB, para generar una publicación sumamente enriquecida, persuasiva y de alto valor para Moodle.

Debes determinar:
1. "categoria_moodle": Clasifica en una de estas 3 opciones:
   - "Eventos" (Si es un webinar, taller, beca en vivo, convocatoria con fecha límite o conferencia)
   - "Interns & Job Offers" (Si es una vacante de empleo, pasantía o convocatoria laboral directa)
   - "Recursos" (Si es un curso, tutorial, artículo, repositorio o herramienta técnica)

2. "nombre": Un título irresistible, profesional y motivador (con emoji inicial, máximo 70 caracteres).

3. "descripcion_html": Estructura HTML rica y detallada que DEBE INCLUIR:
   - <h4>🎓 ¿De qué trata este recurso?</h4> <p>Resumen claro del contenido y sus características principales.</p>
   - <h4>💼 ¿Por qué las empresas y la industria lo solicitan?</h4> <p>Explicación detallada respaldada por la investigación web sobre por qué gigantes tecnológicos o empresas buscan estas habilidades (ej. dominio del inglés, RAG, IA, etc.), impacto en salarios u oportunidades internacionales.</p>
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

    def perform_web_research(self, query: str) -> List[Dict[str, str]]:
        """Realiza una búsqueda web en vivo vía DuckDuckGo para enriquecer el contexto con datos de mercado laboral."""
        results = []
        try:
            keywords = f"{query[:80]} importancia empresas empleo tecnologia STEM"
            print(f"🔍 Investigando en la web: '{keywords}'...")
            with DDGS() as ddgs:
                ddg_res = list(ddgs.text(keywords, max_results=3))
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
        self, texto: str, url: str, research_data: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Motor de enriquecimiento avanzado local utilizando datos web reales si HF falla o no tiene token."""
        texto_lower = texto.lower()

        # Categorización por palabras clave
        if any(w in texto_lower for w in ["webinar", "conferencia", "taller", "presencial", "en vivo", "call", "convocatoria", "solicítala", "fecha límite"]):
            categoria = "Eventos"
            emoji = "📅"
        elif any(w in texto_lower for w in ["job", "intern", "vacante", "empleo", "hiring", "contratando", "postula", "becario", "pasantía", "oferta"]):
            categoria = "Interns & Job Offers"
            emoji = "💼"
        else:
            categoria = "Recursos"
            emoji = "📚"

        # Extraer título destacado
        lineas = [l.strip() for l in texto.split("\n") if l.strip()]
        titulo_raw = lineas[0] if lineas else texto[:50]
        titulo_clean = re.sub(r'^[^\w]+', '', titulo_raw)
        if len(titulo_clean) > 60:
            titulo_clean = titulo_clean[:57] + "..."

        nombre = f"{emoji} {titulo_clean}"

        # Sintetizar resultados de búsqueda de mercado
        mercado_info = ""
        if research_data:
            mercado_info = " ".join([r["snippet"] for r in research_data[:2]])
        else:
            mercado_info = (
                "Empresas líderes en tecnología y consultoría global (como Amazon, Google, Santander y Microsoft) "
                "priorizan candidatos con estas competencias, otorgando hasta un 40% de incremento salarial "
                "y acceso a vacantes remotas o internacionales."
            )

        # Construir descripción rica en HTML
        descripcion_html = (
            f"<h4>🎓 ¿De qué trata este recurso?</h4>"
            f"<p>{texto}</p>"
            f"<h4>💼 ¿Por qué las empresas y la industria lo solicitan?</h4>"
            f"<p><b>Impacto en el mercado laboral:</b> {mercado_info}</p>"
            f"<h4>🚀 Habilidades clave para potenciar tu CV</h4>"
            f"<ul>"
            f"  <li><b>Competitividad Internacional:</b> Dominio y preparación alineados a estándares globales de la industria.</li>"
            f"  <li><b>Perfil de Alto Valor:</b> Diferenciador clave para postulaciones a pasantías, becas y empleos en tecnología.</li>"
            f"  <li><b>Certificación / Acceso:</b> <a href='{url}' target='_blank'>Consulta la convocatoria oficial en este enlace</a>.</li>"
            f"</ul>"
            f"<h4>📌 Recomendación del Profesor</h4>"
            f"<p>Este contenido ha sido seleccionado estratégicamente para estudiantes de MAC y carreras STEM en FES Acatlán. "
            f"Arovechar estas oportunidades durante tu formación universitaria transformará tu empleabilidad al egresar.</p>"
        )

        return {
            "categoria_moodle": categoria,
            "nombre": nombre,
            "descripcion_html": descripcion_html,
            "url": url,
        }

    def adapt_linkedin_post(self, texto: str, url: str) -> Dict[str, Any]:
        """Transforma un post técnico en un recurso universitario enriquecido con IA y Web Research."""
        # 1. Realizar investigación web en tiempo real
        research = self.perform_web_research(texto)
        research_str = "\n".join([f"- {r['title']}: {r['snippet']}" for r in research])

        if not self.hf_token:
            print("HF_TOKEN no configurado. Utilizando motor de investigación y enriquecimiento sintético.")
            return self._fallback_categorize_and_enrich(texto, url, research)

        # 2. Probar pool de modelos de pesos abiertos en Hugging Face
        user_prompt = (
            f"Publicación de origen:\n\"\"\"{texto}\"\"\"\nEnlace: {url}\n\n"
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
                print(f"✅ Enriquecimiento exitoso con modelo '{model_name}'.")
                return data
            except Exception as e:
                print(f"Aviso con modelo '{model_name}': {e}. Probando siguiente modelo...")

        # Fallback si todos los modelos HF están saturados
        return self._fallback_categorize_and_enrich(texto, url, research)
