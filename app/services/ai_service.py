import json
from typing import Dict, Any
from huggingface_hub import InferenceClient
from app.config import config

SYSTEM_PROMPT = """Eres un asistente académico experto para un profesor de Matemáticas Aplicadas y Computación en FES Acatlán (UNAM).
Tu objetivo es tomar publicaciones técnicas (ej. LinkedIn) y enriquecerlas para estudiantes universitarios.

Debes generar:
1. "nombre": Un título atractivo, profesional y claro que llame la atención del estudiante.
2. "descripcion_html": Una descripción enriquecida en HTML que incluya:
   - Resumen del concepto técnico.
   - Puntos clave / Aprendizajes para el estudiante.
   - Por qué es relevante para su formación en ciencias computacionales / ingeniería.

Responde ÚNICAMENTE un JSON válido con esta estructura exacta:
{
  "nombre": "📌 Título Destacado y Relevante",
  "descripcion_html": "<p><b>Contexto:</b> Resumen del tema...</p><p><b>💡 ¿Por qué es relevante para ti?:</b> Explicación del valor para el estudiante...</p>",
  "seccion": 0
}
"""


class AIService:
    def __init__(self):
        self.client = (
            InferenceClient(model=config.HF_MODEL, token=config.HF_TOKEN)
            if config.HF_TOKEN
            else None
        )

    def adapt_linkedin_post(self, texto: str, url: str) -> Dict[str, Any]:
        """Transforma un post técnico de LinkedIn en un recurso educativo enriquecido con IA."""
        if not self.client:
            print("HF_TOKEN no disponible. Usando formateador por defecto.")
            return {
                "nombre": f"💡 Recurso Recomendado: {texto[:45]}...",
                "descripcion_html": f"<p><b>Resumen:</b> {texto}</p><p><i>Recurso complementario de alto valor para estudiantes.</i></p>",
                "seccion": 0,
                "url": url,
            }

        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Post de LinkedIn:\n\"\"\"{texto}\"\"\"\nEnlace: {url}"},
            ]
            res = self.client.chat_completion(
                messages=messages, max_tokens=700, temperature=0.3
            )
            raw = res.choices[0].message.content.strip()

            if raw.startswith("```"):
                raw = raw.split("```json")[-1].split("```")[0].strip()

            data = json.loads(raw)
            data["url"] = url
            return data
        except Exception as e:
            print(f"Error procesando con Hugging Face: {e}")
            return {
                "nombre": "📌 Recurso de IA y Computación Recomendado",
                "descripcion_html": f"<p><b>Resumen:</b> {texto}</p>",
                "seccion": 0,
                "url": url,
            }
