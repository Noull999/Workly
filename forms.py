from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, SelectField, PasswordField, EmailField, DateTimeLocalField, DecimalField, BooleanField, HiddenField
from wtforms.validators import DataRequired, Length, Email, EqualTo, NumberRange, Optional
from models import Category, Warehouse, Service
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
                for c in Category.query.filter_by(company_id=current_user.company_id).all()]  # type: ignore
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

class CompanyForm(FlaskForm):
    name = StringField('Nombre de la Empresa', validators=[DataRequired(), Length(max=100)])
    logo_url = StringField('URL del Logo', validators=[Optional(), Length(max=255)])
    primary_color = StringField('Color Primario', validators=[DataRequired(), Length(min=7, max=7)], default='#007bff')
    secondary_color = StringField('Color Secundario', validators=[DataRequired(), Length(min=7, max=7)], default='#6c757d')

class UserManagementForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired(), Length(min=3, max=64)])
    email = EmailField('Correo Electrónico', validators=[DataRequired(), Email()])
    password = PasswordField('Contraseña', validators=[DataRequired(), Length(min=6)])
    role = SelectField('Rol', choices=[
        ('empleado', 'Empleado'),
        ('admin_empresa', 'Administrador de Empresa'),
        ('admin_global', 'Administrador Global')
    ], validators=[DataRequired()])
    company_id = SelectField('Empresa', coerce=int, validators=[DataRequired()])
    
    def __init__(self, *args, **kwargs):
        super(UserManagementForm, self).__init__(*args, **kwargs)
        # Load companies for admin global users
        from models import Company
        if current_user.is_authenticated and current_user.is_admin_global():
            self.company_id.choices = [(c.id, c.name) for c in Company.query.filter_by(is_active=True).all()]
        elif current_user.is_authenticated:
            # For company admins, only show their own company
            self.company_id.choices = [(current_user.company_id, current_user.company.name)]

class ProfileForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired(), Length(min=3, max=64)])
    email = EmailField('Correo Electrónico', validators=[DataRequired(), Email()])
    current_password = PasswordField('Contraseña Actual', validators=[DataRequired()])
    new_password = PasswordField('Nueva Contraseña', validators=[Optional(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Nueva Contraseña', validators=[
        EqualTo('new_password', message='Las contraseñas deben coincidir')
    ])

class CompanySettingsForm(FlaskForm):
    name = StringField('Nombre de la Empresa', validators=[DataRequired(), Length(max=100)])
    logo_url = StringField('URL del Logo', validators=[Optional(), Length(max=255)])
    primary_color = StringField('Color Primario', validators=[DataRequired(), Length(min=7, max=7)])
    secondary_color = StringField('Color Secundario', validators=[DataRequired(), Length(min=7, max=7)])

class EditAdminCredentialsForm(FlaskForm):
    username = StringField('Nuevo Usuario', validators=[DataRequired(), Length(min=3, max=64)])
    email = EmailField('Nuevo Email', validators=[DataRequired(), Email()])
    password = PasswordField('Nueva Contraseña', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Contraseña', validators=[
        DataRequired(), EqualTo('password', message='Las contraseñas deben coincidir')
    ])


# ===== FORMULARIOS PARA MÓDULOS ADICIONALES =====

class ModuleSettingsForm(FlaskForm):
    """Formulario para activar/desactivar módulos por empresa"""
    module_inventory = BooleanField('Módulo de Inventario')
    module_pos = BooleanField('Módulo POS (Punto de Venta)')
    module_appointments = BooleanField('Módulo de Citas y Reservas')
    module_portfolio = BooleanField('Módulo de Página de Presentación')
    module_scrum = BooleanField('Módulo Scrum Lite')


class ServiceForm(FlaskForm):
    """Formulario para servicios del módulo de citas"""
    name = StringField('Nombre del Servicio', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Descripción', validators=[Optional(), Length(max=500)])
    duration_minutes = IntegerField('Duración (minutos)', validators=[DataRequired(), NumberRange(min=1, max=480)])
    price = DecimalField('Precio', validators=[Optional(), NumberRange(min=0)], places=2)
    is_active = BooleanField('Servicio Activo', default=True)


class AppointmentForm(FlaskForm):
    """Formulario para gestionar citas (interno)"""
    client_name = StringField('Nombre del Cliente', validators=[DataRequired(), Length(max=100)])
    client_phone = StringField('Teléfono', validators=[Optional(), Length(max=50)])
    client_email = EmailField('Email', validators=[Optional(), Email()])
    appointment_date = DateTimeLocalField('Fecha y Hora', validators=[DataRequired()])
    service_id = SelectField('Servicio', coerce=int, validators=[DataRequired()])
    status = SelectField('Estado', choices=[
        ('pendiente', 'Pendiente'),
        ('confirmada', 'Confirmada'),
        ('cancelada', 'Cancelada'),
        ('completada', 'Completada')
    ], default='pendiente')
    notes = TextAreaField('Notas', validators=[Optional(), Length(max=500)])
    
    def __init__(self, *args, **kwargs):
        super(AppointmentForm, self).__init__(*args, **kwargs)
        if current_user.is_authenticated:
            self.service_id.choices = [(s.id, f"{s.name} ({s.duration_minutes} min)") 
                for s in Service.query.filter_by(company_id=current_user.company_id, is_active=True).all()]
        else:
            self.service_id.choices = []


class PublicAppointmentForm(FlaskForm):
    """Formulario para reservas públicas (sin login)"""
    client_name = StringField('Tu Nombre', validators=[DataRequired(), Length(max=100)])
    client_phone = StringField('Tu Teléfono', validators=[DataRequired(), Length(max=50)])
    client_email = EmailField('Tu Email', validators=[Optional(), Email()])
    appointment_date = DateTimeLocalField('Fecha y Hora Deseada', validators=[DataRequired()])
    service_id = SelectField('Servicio', coerce=int, validators=[DataRequired()])
    notes = TextAreaField('Comentarios Adicionales', validators=[Optional(), Length(max=300)])


class PortfolioForm(FlaskForm):
    """Formulario para configurar página de presentación"""
    portfolio_description = TextAreaField('Descripción de la Empresa', validators=[Optional(), Length(max=1000)])
    portfolio_services = TextAreaField('Lista de Servicios/Productos', validators=[Optional(), Length(max=1000)])
    contact_phone = StringField('Teléfono de Contacto', validators=[Optional(), Length(max=50)])
    contact_whatsapp = StringField('WhatsApp', validators=[Optional(), Length(max=50)])
    contact_email = EmailField('Email de Contacto', validators=[Optional(), Email()])
    contact_address = StringField('Dirección', validators=[Optional(), Length(max=200)])
    social_facebook = StringField('Facebook URL', validators=[Optional(), Length(max=200)])
    social_instagram = StringField('Instagram URL', validators=[Optional(), Length(max=200)])
    social_linkedin = StringField('LinkedIn URL', validators=[Optional(), Length(max=200)])


class SaleForm(FlaskForm):
    """Formulario para ventas POS"""
    payment_method = SelectField('Método de Pago', choices=[
        ('efectivo', 'Efectivo'),
        ('tarjeta', 'Tarjeta'),
        ('transferencia', 'Transferencia')
    ], default='efectivo')
    notes = TextAreaField('Notas de la Venta', validators=[Optional(), Length(max=300)])


# ===== POS ADVANCED FORMS =====

class CashSessionForm(FlaskForm):
    """Formulario para apertura de caja"""
    opening_amount = DecimalField('Monto de Apertura ($)', validators=[DataRequired(), NumberRange(min=0)], default=0)
    notes = TextAreaField('Notas de Apertura', validators=[Optional(), Length(max=500)])


class CashSessionCloseForm(FlaskForm):
    """Formulario para cierre de caja"""
    closing_amount = DecimalField('Monto de Cierre ($)', validators=[DataRequired(), NumberRange(min=0)])
    notes = TextAreaField('Notas de Cierre', validators=[Optional(), Length(max=500)])


class CashExpenseForm(FlaskForm):
    """Formulario para egresos de caja"""
    description = StringField('Descripción del Egreso', validators=[DataRequired(), Length(max=200)])
    amount = DecimalField('Monto ($)', validators=[DataRequired(), NumberRange(min=0.01)])
    category = SelectField('Categoría', choices=[
        ('suministros', 'Suministros'),
        ('servicios', 'Servicios'),
        ('mantenimiento', 'Mantenimiento'),
        ('general', 'General')
    ], default='general')
    receipt_number = StringField('Número de Recibo', validators=[Optional(), Length(max=50)])


class MultiPaymentForm(FlaskForm):
    """Formulario para pagos múltiples"""
    # Campos dinámicos que se llenan en JavaScript
    payment_data = HiddenField('Datos de Pago', validators=[DataRequired()])
    notes = TextAreaField('Notas de la Venta', validators=[Optional(), Length(max=300)])
