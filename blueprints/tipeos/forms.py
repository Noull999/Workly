from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Length, Regexp, ValidationError
import re

class TipeoUnificadoForm(FlaskForm):
    stake_username = StringField('Usuario de Stake', validators=[
        DataRequired(message='El nombre de usuario de Stake es obligatorio'),
        Length(min=2, max=100, message='El usuario debe tener entre 2 y 100 caracteres')
    ])
    
    trx_address = StringField('Dirección TRX', validators=[
        DataRequired(message='La dirección TRX es obligatoria'),
        Length(min=30, max=50, message='La dirección TRX debe tener entre 30 y 50 caracteres'),
        Regexp(r'^T[a-zA-Z0-9]{33}$', message='Formato de dirección TRX inválido (debe empezar con T y tener 34 caracteres)')
    ])
    
    tipeo_type = SelectField('Tipo de Tipeo', choices=[
        ('solicitar_tipeo', 'Solicitar Tipeo'),
        ('ganador_tipeo', 'Ganador Tipeo'),
        ('cuenta_nueva', 'Tipeo Cuenta Nueva')
    ], validators=[DataRequired(message='Debes seleccionar un tipo de tipeo')])
    
    image_stake_user = FileField('Imagen Usuario Stake', validators=[
        FileRequired(message='La imagen del usuario de Stake es obligatoria'),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Solo se permiten imágenes (jpg, png, gif, webp)')
    ])
    
    image_sponsor_code = FileField('Imagen Código Patrocinador', validators=[
        FileRequired(message='La imagen del código de patrocinador es obligatoria'),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Solo se permiten imágenes (jpg, png, gif, webp)')
    ])
    
    comments = TextAreaField('Comentarios (opcional)', validators=[
        Length(max=500, message='Los comentarios no pueden superar 500 caracteres')
    ])
