from flask import Flask
from routes.web import web
from routes.api import api

app = Flask(__name__, template_folder="templates", static_folder="static")

# Регистрация blueprint'ов
app.register_blueprint(web)
app.register_blueprint(api, url_prefix="/api")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)