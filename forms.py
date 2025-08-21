from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, SelectField, PasswordField, EmailField
from wtforms.validators import DataRequired, Length, Email, EqualTo, NumberRange, Optional
from models import Category, Warehouse
from flask_login import current_user

class LoginForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired(), Length(min=3, max=64)])
    password = PasswordField('Contraseña', validators=[DataRequired()])

class RegisterForm(FlaskForm):
    company_name = StringField('Nombre de la Empresa', validators=[DataRequired(), Length(min=2, max=100)])
    username = StringField('Usuario', validators=[DataRequired(), Length(min=3, max=64)])
    email = EmailField('Correo Electrónico', validators=[DataRequired(), Email()])
    password = PasswordField('Contraseña', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Confirmar Contraseña', validators=[
        DataRequired(), EqualTo('password', message='Las contraseñas deben coincidir')
    ])

class InventoryItemForm(FlaskForm):
    name = StringField('Nombre del Artículo', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Descripción', validators=[Optional(), Length(max=500)])
    quantity = IntegerField('Cantidad', validators=[DataRequired(), NumberRange(min=0)])
    minimum_stock = IntegerField('Stock Mínimo', validators=[DataRequired(), NumberRange(min=0)])
    sku = StringField('SKU', validators=[Optional(), Length(max=50)])
    barcode = StringField('Código de Barras', validators=[Optional(), Length(max=100)])
    category_id = SelectField('Categoría', coerce=int, validators=[Optional()])
    warehouse_id = SelectField('Almacén', coerce=int, validators=[DataRequired()])
    
    def __init__(self, *args, **kwargs):
        super(InventoryItemForm, self).__init__(*args, **kwargs)
        
        # Load categories and warehouses scoped to current user's company
        if current_user.is_authenticated:
            self.category_id.choices = [(0, 'Sin Categoría')] + [(c.id, c.name) 
                for c in Category.query.filter_by(company_id=current_user.company_id).all()]
            self.warehouse_id.choices = [(w.id, w.name) 
                for w in Warehouse.query.filter_by(company_id=current_user.company_id, is_active=True).all()]
        else:
            self.category_id.choices = [(0, 'Sin Categoría')]
            self.warehouse_id.choices = []

class CategoryForm(FlaskForm):
    name = StringField('Nombre de la Categoría', validators=[DataRequired(), Length(max=64)])
    description = TextAreaField('Descripción', validators=[Optional(), Length(max=200)])

class WarehouseForm(FlaskForm):
    name = StringField('Nombre del Almacén', validators=[DataRequired(), Length(max=100)])
    code = StringField('Código', validators=[DataRequired(), Length(max=20)])
    address = StringField('Dirección', validators=[Optional(), Length(max=200)])
