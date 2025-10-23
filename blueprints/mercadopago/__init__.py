from flask import Blueprint

mercadopago_bp = Blueprint('mercadopago', __name__, url_prefix='/mercadopago')

from . import routes
