from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, SelectField, PasswordField, EmailField, DateTimeLocalField, DecimalField, BooleanField, HiddenField, SubmitField, FieldList, FormField
from wtforms.validators import DataRequired, Length, Email, EqualTo, NumberRange, Optional, ValidationError
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
    price = DecimalField('Precio (Opcional)', validators=[Optional(), NumberRange(min=0)], places=2)
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
    company_email = EmailField('Email Principal de la Empresa', validators=[DataRequired(), Email(), Length(max=120)])
    logo_url = StringField('URL del Logo', validators=[Optional(), Length(max=255)])
    primary_color = StringField('Color Primario', validators=[DataRequired(), Length(min=7, max=7)], default='#007bff')
    secondary_color = StringField('Color Secundario', validators=[DataRequired(), Length(min=7, max=7)], default='#6c757d')
    
    def __init__(self, company_id=None, *args, **kwargs):
        super(CompanyForm, self).__init__(*args, **kwargs)
        self.company_id = company_id  # Para excluir la empresa actual en edición
    
    def validate_company_email(self, field):
        """Validar que el email de empresa sea único"""
        from models import Company
        query = Company.query.filter_by(company_email=field.data)
        
        # Si estamos editando una empresa, excluirla de la búsqueda
        if self.company_id:
            query = query.filter(Company.id != self.company_id)
        
        existing_company = query.first()
        if existing_company:
            raise ValidationError('Este email ya está siendo usado por otra empresa.')

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
    module_notion = BooleanField('Módulo Notion (Wiki Colaborativo)')


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
    opening_amount = DecimalField('Monto de Apertura ($)', validators=[DataRequired(), NumberRange(min=0)])
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


# ===== FORMULARIOS MÓDULO NOTION =====

class NotionPageForm(FlaskForm):
    title = StringField('Título', validators=[DataRequired(), Length(min=1, max=200)])
    icon = StringField('Icono', validators=[Length(max=10)], default='📄')
    is_public = BooleanField('Visible para toda la empresa')
    is_template = BooleanField('Es plantilla')
    parent_id = SelectField('Página padre', coerce=int, validators=[Optional()])
    submit = SubmitField('Crear Página')
    
    def __init__(self, company_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if company_id:
            from models import NotionPage
            pages = NotionPage.query.filter_by(company_id=company_id).all()
            from typing import cast
            self.parent_id.choices = cast(list, [(0, 'Sin página padre')] + [(p.id, p.title) for p in pages])


class NotionBlockForm(FlaskForm):
    block_type = SelectField('Tipo de bloque', choices=[
        ('text', 'Texto'),
        ('heading1', 'Título 1'),
        ('heading2', 'Título 2'),
        ('heading3', 'Título 3'),
        ('list', 'Lista'),
        ('checklist', 'Lista de verificación')
    ], validators=[DataRequired()])
    content = TextAreaField('Contenido', validators=[DataRequired()])
    submit = SubmitField('Agregar Bloque')


class NotionChecklistForm(FlaskForm):
    title = StringField('Título', validators=[DataRequired(), Length(min=1, max=200)])
    description = TextAreaField('Descripción')
    checklist_type = SelectField('Tipo', choices=[
        ('general', 'General'),
        ('inventory_restock', 'Reposición de inventario'),
        ('daily_cash', 'Tareas diarias de caja'),
        ('maintenance', 'Mantenimiento'),
        ('cleaning', 'Limpieza')
    ], validators=[DataRequired()])
    page_id = SelectField('Página asociada', coerce=int, validators=[Optional()])
    submit = SubmitField('Crear Lista')
    
    def __init__(self, company_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if company_id:
            from models import NotionPage
            pages = NotionPage.query.filter_by(company_id=company_id).all()
            from typing import cast
            self.page_id.choices = cast(list, [(0, 'Sin página asociada')] + [(p.id, p.title) for p in pages])


class NotionChecklistItemForm(FlaskForm):
    content = StringField('Tarea', validators=[DataRequired(), Length(min=1, max=500)])
    assignee_id = SelectField('Asignado a', coerce=int, validators=[Optional()])
    due_date = DateTimeLocalField('Fecha límite', validators=[Optional()])
    submit = SubmitField('Agregar Tarea')
    
    def __init__(self, company_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if company_id:
            from models import User
            users = User.query.filter_by(company_id=company_id, active=True).all()
            from typing import cast
            self.assignee_id.choices = cast(list, [(0, 'Sin asignar')] + [(u.id, u.username) for u in users])


class NotionPermissionForm(FlaskForm):
    user_id = SelectField('Usuario', coerce=int, validators=[DataRequired()])
    permission_type = SelectField('Tipo de permiso', choices=[
        ('read', 'Solo lectura'),
        ('edit', 'Editar'),
        ('admin', 'Administrador')
    ], validators=[DataRequired()])
    submit = SubmitField('Otorgar Permiso')
    
    def __init__(self, company_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if company_id:
            from models import User
            users = User.query.filter_by(company_id=company_id, active=True).all()
            self.user_id.choices = [(u.id, u.username) for u in users]


class NotionPageActionForm(FlaskForm):
    """Formulario para acciones de página con protección CSRF"""
    action = HiddenField(validators=[DataRequired()])
    submit = SubmitField()


class NotionDeletePageForm(FlaskForm):
    """Formulario para eliminar página con confirmación"""
    confirm = StringField('Confirmación', validators=[
        DataRequired(message='Debes escribir DELETE para confirmar'),
        EqualTo('confirm_value', message='Debes escribir exactamente DELETE')
    ])
    confirm_value = HiddenField(default='DELETE')
    submit = SubmitField('Eliminar Página')


class NotionBlockActionForm(FlaskForm):
    """Formulario para acciones de bloque con protección CSRF"""
    action = HiddenField(validators=[DataRequired()])
    submit = SubmitField()


class ModuleLinkForm(FlaskForm):
    target_module = SelectField('Módulo destino', choices=[
        ('inventory', 'Inventario'),
        ('pos', 'POS'),
        ('appointments', 'Citas'),
        ('scrum', 'Scrum Lite'),
        ('notion', 'Notion')
    ], validators=[DataRequired()])
    target_id = IntegerField('ID del elemento', validators=[DataRequired()])
    link_type = SelectField('Tipo de enlace', choices=[
        ('reference', 'Referencia'),
        ('dependency', 'Dependencia'),
        ('related', 'Relacionado')
    ], validators=[DataRequired()])
    description = StringField('Descripción', validators=[Length(max=200)])
    submit = SubmitField('Crear Enlace')


class RaffleForm(FlaskForm):
    """Formulario para crear sorteos con puntos de Kick"""
    title = StringField('Título del Sorteo', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Descripción', validators=[Optional(), Length(max=500)])
    prize = StringField('Premio', validators=[DataRequired(), Length(max=300)])
    entry_cost = IntegerField('Costo de Entrada (Puntos de Kick)', validators=[DataRequired(), NumberRange(min=1)])
    max_entries = IntegerField('Máximo de Participantes (Opcional)', validators=[Optional(), NumberRange(min=1)])
    end_date = DateTimeLocalField('Fecha de Cierre (Opcional)', validators=[Optional()], format='%Y-%m-%dT%H:%M')
    submit = SubmitField('Crear Sorteo')


class ClipForm(FlaskForm):
    """Formulario para gestionar clips de video"""
    video_url = StringField('URL del Video', validators=[DataRequired(), Length(max=500)])
    title = StringField('Título', validators=[Optional(), Length(max=200)])
    description = TextAreaField('Descripción', validators=[Optional(), Length(max=500)])
    thumbnail_url = StringField('URL de Miniatura', validators=[Optional(), Length(max=500)])
    featured_thumbnail_url = StringField('URL de Miniatura Destacada', validators=[Optional(), Length(max=500)])
    is_featured = BooleanField('Marcar como Destacado')
    order_position = IntegerField('Posición de Orden', validators=[Optional(), NumberRange(min=0)], default=0)
    submit = SubmitField('Guardar Clip')
