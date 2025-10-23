from flask import Blueprint

stripe_bp = Blueprint('stripe', __name__, url_prefix='/stripe')

from . import routes
