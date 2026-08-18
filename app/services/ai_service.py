import json
import re
from typing import Dict, Any
from huggingface_hub import InferenceClient
from app.config import config

SYSTEM_PROMPT = """Eres un asistente académico universitario experto para la carrera de Matemáticas Aplicadas y Computación en FES Acatlán (UNAM).
Tu misión es tomar una publicación técnica de LinkedIn y adaptarla para colocarla en la plataforma Moodle del curso.

Debes determinar:
1. "categoria_moodle": Clasifica la publicación en exactamente una de estas 3 secciones:
   - "Eventos" (Si es un webinar, taller, conferencia, evento presencial o en vivo)
   - "Interns & Job Offers" (Si es una vacante, pasantía, empleo, prácticas profesionales o convocatoria laboral)
   - "Recursos" (Si es un artículo, curso, tutorial, herramienta, repositorio o material de estudio)

2. "nombre": Un título altamente atractivo, profesional y motivador para estudiantes universiarios (máximo 70 caracteres, con emoji inicial).

3. "descripcion_html": Formato HTML limpio y bien estructurado que incluya:
   - <h4>🎓 Contexto y Resumen</h4> <p>Explicación clara en 2 párrafos del contenido.</p>
   - <h4>🚀 Lo que aprenderás / Puntos Clave</h4> <ul><li>Punto 1</li><li>Punto 2</li><li>Punto 3</li></ul>
   - <h4>💡 ¿Por qué debes revisar este contenido?</h4> <p>Explicación persuasiva del impacto en su perfil académico y profesional.</p>

Responde ÚNICAMENTE un JSON válido con esta estructura exacta:
{
  "categoria_moodle": "Recursos",
  "nombre": "🚀 Título Atractivo y Destacado",
  "descripcion_html": "<h4>🎓 Contexto y Resumen</h4><p>...</p><h4>🚀 Puntos Clave</h4><ul><li>...</li></ul><h4>💡 ¿Por qué debes revisar este contenido?</h4><p>...</p>"
}
"""


class AIService:
    def __init__(self):
        self.client = (
            InferenceClient(model=config.HF_MODEL, token=config.HF_TOKEN)
            if config.HF_TOKEN
            else None
        )

    def _fallback_categorize_and_enrich(self, texto: str, url: str) -> Dict[str, Any]:
        """Formateador y clasificador local inteligente cuando HF no está disponible o falla."""
        texto_lower = texto.lower()

        # Determinar categoría por palabras clave
        if any(w in texto_lower for w in ["webinar", "conferencia", "taller", "presencial", "en vivo", "event", "summit", "meetup", "registro"]):
            categoria = "Eventos"
            emoji = "📅"
        elif any(w in texto_lower for w in ["job", "intern", "vacante", "empleo", "hiring", "contratando", "postula", "becario", "pasantía", "oferta"]):
            categoria = "Interns & Job Offers"
            emoji = "💼"
        else:
            categoria = "Recursos"
            emoji = "📚"

        # Extraer una primera línea limpia para el título
        lineas = [l.strip() for l in texto.split("\n") if l.strip()]
        titulo_base = lineas[0] if lineas else texto[:50]
        titulo_base = re.sub(r'^[^\w]+', '', titulo_base) # Limpiar caracteres iniciales
        if len(titulo_base) > 65:
            titulo_base = titulo_base[:62] + "..."

        nombre = f"{emoji} {titulo_base}"

        # Construir descripción HTML enriquecida
        descripcion_html = (
            f"<h4>🎓 Contexto y Resumen</h4>"
            f"<p>{texto}</p>"
            f"<h4>🚀 Puntos Clave y Beneficios</h4>"
            f"<ul>"
            f"  <li><b>Actualización Profesional:</b> Información relevante del sector tecnológico actual.</li>"
            f"  <li><b>Aplicación Práctica:</b> Conocimientos directamente aplicables a proyectos de desarrollo y ciencias computacionales.</li>"
            f"  <li><b>Enlace Directo:</b> Revisa la publicación completa en <a href='{url}' target='_blank'>este enlace</a>.</li>"
            f"</ul>"
            f"<h4>💡 ¿Por qué debes revisar este contenido?</h4>"
            f"<p>Este recurso ha sido seleccionado por tu profesor para complementar tus clases en FES Acatlán, ayudándote a fortalecer tu perfil profesional en la industria de la tecnología y computación.</p>"
        )

        return {
            "categoria_moodle": categoria,
            "nombre": nombre,
            "descripcion_html": descripcion_html,
            "url": url,
        }

    def adapt_linkedin_post(self, texto: str, url: str) -> Dict[str, Any]:
        """Transforma un post técnico de LinkedIn en un recurso educativo estructurado con IA."""
        if not self.client:
            print("HF_TOKEN no configurado. Utilizando motor de enriquecimiento local.")
            return self._fallback_categorize_and_enrich(texto, url)

        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Post de LinkedIn:\n\"\"\"{texto}\"\"\"\nEnlace: {url}"},
            ]
            res = self.client.chat_completion(
                messages=messages, max_tokens=900, temperature=0.3
            )
            raw = res.choices[0].message.content.strip()

            if "```" in raw:
                raw = raw.split("```json")[-1].split("```")[0].strip()

            data = json.loads(raw)
            data["url"] = url
            if "categoria_moodle" not in data:
                data["categoria_moodle"] = "Recursos"
            return data
        except Exception as e:
            print(f"Aviso al procesar con Hugging Face ({e}). Usando motor de enriquecimiento alternativo.")
            return self._fallback_categorize_and_enrich(texto, url)
