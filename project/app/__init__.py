from flask import Flask

from app.config import Config
from app.controllers.health_controller import health_bp
from app.controllers.news_controller import news_bp
from app.controllers.search_controller import search_bp
from app.extensions import init_extensions


def create_app(config_class: type[Config] = Config) -> Flask:
    """Фабрика для создания приложения Flask"""

    # Создаем экземпляр приложения Flask
    app = Flask(__name__, instance_relative_config=True)
    # Загружаем конфигурацию из переданного класса
    app.config.from_object(config_class)

    # Инициализируем расширения и необходимые компоненты
    init_extensions(app)
    # Регистрируем blueprint для эндпоинов
    app.register_blueprint(health_bp)
    app.register_blueprint(news_bp)
    app.register_blueprint(search_bp)

    # Главная страница приложения
    @app.get("/")
    def index():
        from flask import render_template
        # Рендерим шаблон index.html
        return render_template("index.html")

    # Возвращаем готовое приложение
    return app
