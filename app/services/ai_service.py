import json
from typing import Dict, Any
from huggingface_hub import InferenceClient
from app.config import config

SYSTEM_PROMPT = """Eres un asistente académico para un profesor de Matemáticas Aplicadas y Computación en FES Acatlán.
Recibes una publicación técnica de LinkedIn y debes adaptarla para Moodle.
Responde ÚNICAMENTE un JSON válido con esta estructura exacta:
{
  "tipo": "recurso_url",
  "titulo": "Título profesional y claro",
  "contenido_html": "<p>Breve contexto educativo para los estudiantes.</p>",
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
        """Transforma un post técnico de LinkedIn en un recurso educativo estructurado."""
        if not self.client:
            print("HF_TOKEN no disponible. Usando formateador por defecto.")
            return {
                "tipo": "recurso_url",
                "titulo": f"Recurso: {texto[:40]}...",
                "contenido_html": f"<p>{texto}</p>",
                "seccion": 0,
                "url": url,
            }

        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Post de LinkedIn:\n\"\"\"{texto}\"\"\"\nEnlace: {url}"},
            ]
            res = self.client.chat_completion(
                messages=messages, max_tokens=600, temperature=0.2
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
                "tipo": "recurso_url",
                "titulo": "Recurso sobre IA / Computación",
                "contenido_html": f"<p>{texto}</p>",
                "seccion": 0,
                "url": url,
            }
