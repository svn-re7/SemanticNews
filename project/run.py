from app import create_app
from app.controllers.ingestion_controller import start_auto_ingestion_if_needed


app = create_app()


if __name__ == "__main__":
    # Автообновление запускается только в реальной точке входа, чтобы импорт app в тестах не стартовал сеть.
    start_auto_ingestion_if_needed()
    app.run(debug=True, use_reloader=False)
