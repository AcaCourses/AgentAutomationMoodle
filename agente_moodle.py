import os
import json
from playwright.sync_api import sync_playwright
from app.config import config
from app.services.moodle_service import MoodleService


def main():
    if not config.MOODLE_USER or not config.MOODLE_PASS or config.MOODLE_USER == "tu_usuario_o_correo":
        print("Configuración pendiente: Por favor edita el archivo .env con tus credenciales reales.")
        return

    if not os.path.exists(config.JSON_DATA_FILE):
        print(f"Error: No se encontró el archivo de datos {config.JSON_DATA_FILE}")
        return

    with open(config.JSON_DATA_FILE, "r", encoding="utf-8") as f:
        recursos = json.load(f)

    pendientes = [item for item in recursos if not item.get("publicado")]
    if not pendientes:
        print("No hay recursos pendientes por publicar en recursos.json.")
        return

    print(f"Se encontraron {len(pendientes)} elemento(s) pendiente(s) por publicar.")

    moodle = MoodleService()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        if os.path.exists(config.SESSION_FILE):
            context = browser.new_context(storage_state=config.SESSION_FILE)
        else:
            context = browser.new_context()

        page = context.new_page()
        moodle.ensure_authenticated(page, context)

        actualizados = False
        for item in recursos:
            if item.get("publicado"):
                continue

            try:
                tipo = item.get("tipo", "recurso_url")
                if tipo == "recurso_url":
                    moodle.publish_url_resource(page, item)
                    item["publicado"] = True
                    actualizados = True
                elif tipo == "anuncio_foro":
                    moodle.publish_forum_announcement(page, item)
                    item["publicado"] = True
                    actualizados = True
            except Exception as e:
                print(f"Error publicando '{item.get('nombre') or item.get('asunto')}': {e}")

        if actualizados:
            with open(config.JSON_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(recursos, f, indent=2, ensure_ascii=False)
            print("Archivo recursos.json actualizado con éxito.")

        browser.close()


if __name__ == "__main__":
    main()
