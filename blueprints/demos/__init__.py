from flask import Blueprint

demos_bp = Blueprint('demos', __name__, url_prefix='/demos')

from . import routes
