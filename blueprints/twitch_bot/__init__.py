from flask import Blueprint

twitch_bot = Blueprint('twitch_bot', __name__, url_prefix='/twitch-bot')

from . import routes
