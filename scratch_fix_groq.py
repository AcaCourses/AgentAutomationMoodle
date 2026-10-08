import re

filepath = 'd:/dr871/Projects/AgentAutomationMoodle/app/services/ai_service.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Extract the misplaced gemini methods
gemini_methods_start = content.find("    def enforce_gemini_rate_limit(self, cb:")
gemini_methods_end = content.find("        return None", content.find("def call_gemini_api(")) + len("        return None")

gemini_methods = content[gemini_methods_start:gemini_methods_end]

# 2. Remove them from their current position
content = content[:gemini_methods_start] + content[gemini_methods_end:]

# 3. Find the actual end of call_groq_api (which is now right after the second 'return None' from the groq loop)
# Wait, if we removed the gemini block, the rest of call_groq_api starts right after `if not self.groq_keys:\n            return None\n\n`
# Then we have `        self.enforce_rate_limit(cb)\n\n        for attempt in range(len(self.groq_keys)):`
# It ends with `        return None`

# Since we just sliced it out, the file now has `call_groq_api` intact but we need to insert `gemini_methods` AFTER `call_groq_api`.
# Let's find the end of call_groq_api
end_of_groq_api = content.find("    def parse_linkedin_iframe")
if end_of_groq_api != -1:
    content = content[:end_of_groq_api] + "\n" + gemini_methods + "\n\n" + content[end_of_groq_api:]

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print("Done fixing ai_service.py")
