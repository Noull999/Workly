from app import app
import os

if __name__ == '__main__':
    # Puerto configurable desde variable de entorno
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

    # Inicia la app
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
