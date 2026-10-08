import sys

filepath = 'd:/dr871/Projects/AgentAutomationMoodle/app/services/ai_service.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace imports
content = content.replace('from huggingface_hub import InferenceClient\n', '')

# 2. Replace models pools
old_pools = """GEMINI_MODELS_POOL = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash-exp",
    "gemini-1.5-flash-8b",
]

HF_MODELS_POOL = [
    "mistralai/Mistral-7B-Instruct-v0.2",
    "HuggingFaceH4/zephyr-7b-beta",
    "Qwen/Qwen2.5-Coder-7B-Instruct",
    "meta-llama/Meta-Llama-3-8B-Instruct",
]"""
new_pools = """GROQ_MODELS_POOL = [
    "llama-3.3-70b-versatile",
    "mixtral-8x7b-32768",
    "llama-3.1-8b-instant",
]"""
content = content.replace(old_pools, new_pools)


old_init_and_call = """    def __init__(self):
        self.gemini_key = config.GEMINI_API_KEY
        self.hf_tokens = config.HF_TOKENS
        self.hf_token = self.hf_tokens[0] if self.hf_tokens else config.HF_TOKEN
        self.last_gemini_call = 0.0

    def _log(self, msg: str, level: str = "info", cb: Optional[Callable[[str, str], None]] = None):
        print(msg)
        if cb:
            try:
                cb(msg, level)
            except Exception:
                pass

    def enforce_gemini_rate_limit(self, cb: Optional[Callable[[str, str], None]] = None):
        \"\"\"Pausa estratégica de 4.5 segundos para no exceder jamás el límite estricto de 15 RPM en Gemini.\"\"\"
        now = time.time()
        elapsed = now - self.last_gemini_call
        if elapsed < 4.5:
            sleep_time = 4.5 - elapsed
            self._log(f"⏱️ Guardián de Rate Limit Gemini: Pausa preventiva de {sleep_time:.2f}s...", "info", cb)
            time.sleep(sleep_time)
        self.last_gemini_call = time.time()

    def call_gemini_api(
        self, system_prompt: str, user_prompt: str, cb: Optional[Callable[[str, str], None]] = None
    ) -> Optional[Dict[str, Any]]:
        \"\"\"Llama a la API de Google AI Studio Gemini con garantía de JSON estructurado y control estricto de cuota.\"\"\"
        if not self.gemini_key or self.gemini_key == "tu_gemini_api_key_aqui":
            return None

        self.enforce_gemini_rate_limit(cb)

        for model_name in GEMINI_MODELS_POOL:
            try:
                self._log(f"🌟 Solicitando enriquecimiento a Google AI Studio: '{model_name}'...", "info", cb)
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
                            self._log(f"✅ Enriquecimiento exitoso con Google AI Studio Gemini ('{model_name}').", "success", cb)
                            return parsed
                    elif response.status_code == 429:
                        self._log(f"⚠️ Rate limit 429 alcanzado en Gemini ('{model_name}'). Probando siguiente modelo...", "warn", cb)
                    else:
                        self._log(f"Aviso en Gemini ('{model_name}'): HTTP {response.status_code} - {response.text[:150]}", "warn", cb)
            except Exception as e:
                self._log(f"Aviso al consultar Google AI Studio ({model_name}): {e}", "warn", cb)

        return None"""

new_init_and_call = """    def __init__(self):
        self.groq_keys = config.GROQ_API_KEYS
        self.current_key_idx = 0
        self.last_call = 0.0

    def _log(self, msg: str, level: str = "info", cb: Optional[Callable[[str, str], None]] = None):
        print(msg)
        if cb:
            try:
                cb(msg, level)
            except Exception:
                pass

    def get_next_groq_key(self):
        if not self.groq_keys:
            return None
        key = self.groq_keys[self.current_key_idx]
        self.current_key_idx = (self.current_key_idx + 1) % len(self.groq_keys)
        return key

    def enforce_rate_limit(self, cb: Optional[Callable[[str, str], None]] = None):
        now = time.time()
        elapsed = now - self.last_call
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        self.last_call = time.time()

    def call_groq_api(
        self, system_prompt: str, user_prompt: str, is_json: bool = True, cb: Optional[Callable[[str, str], None]] = None
    ) -> Optional[Dict[str, Any]]:
        \"\"\"Llama a la API de Groq con balanceo entre los 2 tokens configurados.\"\"\"
        if not self.groq_keys:
            return None

        self.enforce_rate_limit(cb)

        for attempt in range(len(self.groq_keys)):
            token = self.get_next_groq_key()
            if not token:
                continue

            for model_name in GROQ_MODELS_POOL:
                try:
                    self._log(f"🌟 Solicitando enriquecimiento a Groq: '{model_name}' con Token #{self.current_key_idx}...", "info", cb)
                    endpoint = "https://api.groq.com/openai/v1/chat/completions"
                    
                    payload = {
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": 0.2,
                        "max_tokens": 1100
                    }
                    if is_json:
                        payload["response_format"] = {"type": "json_object"}

                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    }

                    with httpx.Client(timeout=15.0) as client:
                        response = client.post(endpoint, json=payload, headers=headers)
                        if response.status_code == 200:
                            res_data = response.json()
                            content = res_data["choices"][0]["message"]["content"]
                            if is_json:
                                parsed = json.loads(content, strict=False)
                                self._log(f"✅ Enriquecimiento exitoso con Groq ('{model_name}').", "success", cb)
                                return parsed
                            return {"text": content}
                        elif response.status_code == 429:
                            self._log(f"⚠️ Rate limit 429 alcanzado en Groq ('{model_name}'). Probando siguiente token...", "warn", cb)
                            break
                        else:
                            self._log(f"Aviso en Groq ('{model_name}'): HTTP {response.status_code} - {response.text[:150]}", "warn", cb)
                except Exception as e:
                    self._log(f"Aviso al consultar Groq ({model_name}): {e}", "warn", cb)

        return None"""

content = content.replace(old_init_and_call, new_init_and_call)

# Now replace adapt_linkedin_post completely
# We'll just find the start of adapt_linkedin_post and the start of parse_chat_message
import re

start_adapt = content.find("    def adapt_linkedin_post(")
start_parse = content.find("    def parse_chat_message(")

if start_adapt != -1 and start_parse != -1:
    new_adapt_post = """    def adapt_linkedin_post(
        self, texto: str, url: str, empresa_input: Optional[str] = None, linkedin_url: Optional[str] = None, cb: Optional[Callable[[str, str], None]] = None
    ) -> Dict[str, Any]:
        \"\"\"
        Jerarquía de Ejecución optimizada (Groq + Respaldos):
        \"\"\"
        logo_info = self.resolve_company_logo(empresa_input, url, texto, cb=cb)
        empresa_name = logo_info["nombre_empresa"]

        research = self.perform_web_research(texto[:60], empresa_name, cb=cb)
        research_str = "\\n".join([f"- {r['title']}: {r['snippet']}" for r in research])

        texto_lower = texto.lower()
        is_task = (
            "canva.link" in url.lower()
            or "canva.com" in url.lower()
            or "canva.link" in texto_lower
            or "canva.com" in texto_lower
        )
        is_course = any(w in texto_lower for w in ["curso", "course", "aprender", "aprender inglés", "idiomas", "beca de estudio", "tutorial", "capacitación"])
        is_job_post = (
            any(w in texto_lower for w in [
                "we are hiring", "job description", "vacante de empleo",
                "oferta de empleo", "hiring software", "job vacancy",
                "sde intern", "puesto de trabajo", "postúlate a la vacante"
            ]) and not is_course and not is_task
        )

        active_system_prompt = JOB_OFFER_SYSTEM_PROMPT if is_job_post else GENERAL_SYSTEM_PROMPT
        if is_task:
            self._log("📝 Detectada Asignación / Tarea de Canva. Clasificando para sección Tareas con límite de 15 días.", "info", cb)
        elif is_job_post:
            self._log("💼 Detectada Oferta de Empleo / Job Post. Utilizando Prompt Especializado de Autoevaluación y Roadmap.", "info", cb)

        user_prompt = (
            f"Empresa Convocante / Plataforma: {empresa_name}\\n"
            f"Publicación de origen:\\n\\\"\\\"\\\"{texto}\\\"\\\"\\\"\\nEnlace de Registro / Destino: {url}\\n\\n"
            f"Datos de Investigación Web sobre {empresa_name} y Mercado:\\n{research_str}"
        )

        groq_res = self.call_groq_api(active_system_prompt, user_prompt, cb=cb)
        if groq_res:
            groq_res["url"] = url
            if is_task:
                groq_res["categoria_moodle"] = "Tareas"
            elif is_job_post:
                groq_res["categoria_moodle"] = "Interns & Job Offers"
            elif groq_res.get("categoria_moodle") == "Tareas":
                groq_res["categoria_moodle"] = "Recursos"
            elif is_course and groq_res.get("categoria_moodle") == "Interns & Job Offers":
                groq_res["categoria_moodle"] = "Recursos"

            groq_res["nombre"] = self.format_title_with_date(groq_res.get("nombre", "Recurso Destacado"))
            groq_res["descripcion_html"] = self.attach_header_to_html(
                groq_res.get("descripcion_html", ""), logo_info, linkedin_url, cb=cb
            )
            groq_res["empresa"] = empresa_name
            return groq_res

        self._log("💡 Utilizando Motor Sintético Local de Respaldo.", "info", cb)
        return self._fallback_categorize_and_enrich(texto, url, research, logo_info, linkedin_url, cb=cb)

"""
    content = content[:start_adapt] + new_adapt_post + content[start_parse:]

# Update parse_chat_message to call groq instead of gemini
content = content.replace(
    "parsed = self.call_gemini_api(CHAT_PARSER_SYSTEM_PROMPT, message, cb=cb)",
    "parsed = self.call_groq_api(CHAT_PARSER_SYSTEM_PROMPT, message, cb=cb)"
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print("Done writing modifications to ai_service")
