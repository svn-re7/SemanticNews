from flask import Blueprint, jsonify


health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health_check():
    """Simple health endpoint to verify app is running."""
    return jsonify({"status": "ok"})
