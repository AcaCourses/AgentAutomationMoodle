from pyngrok import ngrok
from app.config import config


def setup_ngrok_tunnel(port: int = 8000) -> None:
    """Configura e inicia un túnel público de ngrok si NGROK_AUTHTOKEN está definido."""
    if config.NGROK_AUTHTOKEN and config.NGROK_AUTHTOKEN != "tu_ngrok_authtoken":
        try:
            ngrok.set_auth_token(config.NGROK_AUTHTOKEN)
            tunnel = ngrok.connect(port)
            print(f"\n🚀 TU URL PÚBLICA DE NGROK ES: {tunnel.public_url}")
            print(f"👉 Endpoint listo: {tunnel.public_url}/webhook-linkedin\n")
        except Exception as e:
            print(f"Aviso Ngrok: {e}")
    else:
        print(f"\n💡 Ngrok no configurado. El servidor local correrá en http://localhost:{port}")
        print(f"👉 Endpoint local: http://localhost:{port}/webhook-linkedin\n")
