from flask import Blueprint

tipeos_bp = Blueprint('tipeos', __name__, url_prefix='/tipeos')

from . import routes
