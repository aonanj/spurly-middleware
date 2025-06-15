from config import Config
from flask import Flask, current_app
from flask_cors import CORS
from infrastructure.clients import init_clients
from infrastructure.logger import setup_logger
from routes.connections import connection_bp
from routes.context_route import context_bp
from routes.conversations import conversations_bp
from routes.spurs import spurs_bp
from routes.feedback import feedback_bp
from routes.message_engine import generate_bp
from routes.ocr import ocr_bp
from routes.onboarding import onboarding_bp
from routes.user_management import user_management_bp
from routes.auth_routes import auth_bp
from routes.social_auth import social_auth_bp
from routes.profile_routes import profile_bp
from dotenv import load_dotenv

def create_app():
    app = Flask(__name__)
    CORS(app)

    @app.route('/health')
    def health():
        return {'status': 'healthy'}, 200
    load_dotenv()
    app.config.from_object("config.Config")
    app.register_blueprint(auth_bp)
    app.register_blueprint(social_auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(onboarding_bp)
    app.register_blueprint(ocr_bp)
    app.register_blueprint(spurs_bp)
    app.register_blueprint(connection_bp)
    app.register_blueprint(feedback_bp)
    app.register_blueprint(conversations_bp)
    app.register_blueprint(user_management_bp)
    app.register_blueprint(context_bp)
    app.register_blueprint(generate_bp)

    level = app.config.get("LOGGER_LEVEL", "INFO")
    setup_logger(name="spurly", level=level, toFile=True, fileName="spurly.log")

    return app

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        init_clients(app)
    app.run(host="0.0.0.0", port=8080)
