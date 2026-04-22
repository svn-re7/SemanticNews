from flask import Blueprint, jsonify


health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health_check():
    """Вернуть простой технический статус приложения."""
    return jsonify({"status": "ok"})
