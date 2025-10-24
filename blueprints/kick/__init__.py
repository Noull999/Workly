from flask import Blueprint

kick_bp = Blueprint('kick', __name__, url_prefix='/kick')

from . import routes
