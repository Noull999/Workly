from flask import Blueprint

kick_bot = Blueprint('kick_bot', __name__, url_prefix='/kick-bot')

from . import routes
