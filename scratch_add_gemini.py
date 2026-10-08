import sys, re

filepath = 'd:/dr871/Projects/AgentAutomationMoodle/app/services/ai_service.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add GEMINI_MODELS_POOL under GROQ_MODELS_POOL
new_pools = """GROQ_MODELS_POOL = [
    "llama-3.3-70b-versatile",
    "mixtral-8x7b-32768",
    "llama-3.1-8b-instant",
]

GEMINI_MODELS_POOL = [
    "gemini-2.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash-exp",
    "gemini-1.5-flash-8b",
]"""
content = content.replace('GROQ_MODELS_POOL = [\n    "llama-3.3-70b-versatile",\n    "mixtral-8x7b-32768",\n    "llama-3.1-8b-instant",\n]', new_pools)

# 2. Add self.gemini_key in __init__
init_old = """    def __init__(self):
        self.groq_keys = config.GROQ_API_KEYS
        self.current_key_idx = 0
        self.last_call = 0.0"""
init_new = """    def __init__(self):
        self.groq_keys = config.GROQ_API_KEYS
        self.gemini_key = config.GEMINI_API_KEY
        self.current_key_idx = 0
        self.last_call = 0.0
        self.last_gemini_call = 0.0"""
content = content.replace(init_old, init_new)

# 3. Add enforce_gemini_rate_limit and call_gemini_api right after call_groq_api
call_groq_end_idx = content.find("        return None", content.find("def call_groq_api(")) + len("        return None")

gemini_methods = """

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
        \"\"\"Llama a la API de Google AI Studio Gemini.\"\"\"
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

content = content[:call_groq_end_idx] + gemini_methods + content[call_groq_end_idx:]

# 4. Modify adapt_linkedin_post to try groq then gemini
fallback_call_old = """        groq_res = self.call_groq_api(active_system_prompt, user_prompt, cb=cb)
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
        return self._fallback_categorize_and_enrich(texto, url, research, logo_info, linkedin_url, cb=cb)"""

fallback_call_new = """        groq_res = self.call_groq_api(active_system_prompt, user_prompt, cb=cb)
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
            
        gemini_res = self.call_gemini_api(active_system_prompt, user_prompt, cb=cb)
        if gemini_res:
            gemini_res["url"] = url
            if is_task:
                gemini_res["categoria_moodle"] = "Tareas"
            elif is_job_post:
                gemini_res["categoria_moodle"] = "Interns & Job Offers"
            elif gemini_res.get("categoria_moodle") == "Tareas":
                gemini_res["categoria_moodle"] = "Recursos"
            elif is_course and gemini_res.get("categoria_moodle") == "Interns & Job Offers":
                gemini_res["categoria_moodle"] = "Recursos"

            gemini_res["nombre"] = self.format_title_with_date(gemini_res.get("nombre", "Recurso Destacado"))
            gemini_res["descripcion_html"] = self.attach_header_to_html(
                gemini_res.get("descripcion_html", ""), logo_info, linkedin_url, cb=cb
            )
            gemini_res["empresa"] = empresa_name
            return gemini_res

        self._log("💡 Utilizando Motor Sintético Local de Respaldo.", "info", cb)
        return self._fallback_categorize_and_enrich(texto, url, research, logo_info, linkedin_url, cb=cb)"""
content = content.replace(fallback_call_old, fallback_call_new)

# 5. Modify parse_chat_message
parse_chat_old = """        # 1. Intentar llamar a Gemini o Hugging Face
        parsed = self.call_groq_api(CHAT_PARSER_SYSTEM_PROMPT, message, cb=cb)
        if not parsed:"""
parse_chat_new = """        # 1. Intentar llamar a Groq, si falla, Gemini
        parsed = self.call_groq_api(CHAT_PARSER_SYSTEM_PROMPT, message, cb=cb)
        if not parsed:
            parsed = self.call_gemini_api(CHAT_PARSER_SYSTEM_PROMPT, message, cb=cb)
        if not parsed:"""
content = content.replace(parse_chat_old, parse_chat_new)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print("Done writing modifications for gemini 2.5 flash to ai_service")
