from flask import Blueprint

scrum = Blueprint('scrum', __name__)

from . import routes