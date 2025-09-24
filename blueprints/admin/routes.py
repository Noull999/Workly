from flask import render_template, redirect, url_for, flash, request, g
from flask_login import login_required, current_user
from datetime import datetime, date
from sqlalchemy.exc import IntegrityError
from . import admin
from ..decorators import admin_global_required, admin_required
from models import User, Company, Warehouse
from forms import CompanyForm, UserManagementForm, EditAdminCredentialsForm, ModuleSettingsForm
from utils import setup_new_company, validate_company_access
from app import db

@admin.route('/dashboard')
@login_required
@admin_global_required
def dashboard():
    """Dashboard principal para super admin"""
    companies = Company.query.all()
    users = User.query.all()
    total_companies = len(companies)
    total_users = len(users)
    active_companies = len([c for c in companies if c.is_active])
    
    # Estadísticas de uso de módulos
    module_stats = {
        'inventory': sum(1 for c in companies if c.module_inventory and c.is_active),
        'pos': sum(1 for c in companies if c.module_pos and c.is_active),
        'appointments': sum(1 for c in companies if c.module_appointments and c.is_active),
        'portfolio': sum(1 for c in companies if c.module_portfolio and c.is_active),
        'scrum': sum(1 for c in companies if c.module_scrum and c.is_active),
        'notion': sum(1 for c in companies if c.module_notion and c.is_active)
    }
    
    modules_active = sum(module_stats.values())
    
    # Empresas más recientes
    recent_companies = Company.query.order_by(Company.created_at.desc()).limit(5).all()
    
    return render_template('admin/dashboard.html',
                         companies=companies,
                         recent_companies=recent_companies,
                         total_companies=total_companies,
                         total_users=total_users,
                         active_companies=active_companies,
                         modules_active=modules_active,
                         module_stats=module_stats)

@admin.route('/companies', methods=['GET', 'POST'])
@login_required
@admin_global_required
def manage_companies():
    """Gestión de empresas - crear, editar, listar"""
    form = CompanyForm()
    if form.validate_on_submit():
        # Generar código único
        code = Company.generate_code()
        
        company = Company(
            name=form.name.data,
            code=code,
            company_email=form.company_email.data,
            logo_url=form.logo_url.data if form.logo_url.data else None,
            primary_color=form.primary_color.data,
            secondary_color=form.secondary_color.data
        )
        db.session.add(company)
        db.session.flush()  # Get company ID
        
        # Crear admin automático para la empresa
        admin_user = User(
            username=f"admin_{code.lower()}",
            email=f"admin@{company.name.lower().replace(' ', '')}.com",
            role='admin_empresa',
            company_id=company.id
        )
        # Generar contraseña inicial predecible y segura
        temp_password = f"{company.name.lower().replace(' ', '')}123"
        admin_user.set_password(temp_password)
        db.session.add(admin_user)
        
        # Crear almacén principal automático
        warehouse = Warehouse(
            name='Almacén Principal',
            code='MAIN',
            address='Almacén principal de la empresa',
            company_id=company.id
        )
        db.session.add(warehouse)
        
        try:
            db.session.commit()
            flash(f'¡Empresa "{company.name}" creada exitosamente! Usuario admin: {admin_user.username}, contraseña inicial: {temp_password}. IMPORTANTE: Cambia la contraseña usando "Credenciales".', 'warning')
            return redirect(url_for('admin.manage_companies'))
        except IntegrityError as e:
            db.session.rollback()
            # Verificar si es error de constraint de email único
            if 'uq_company_company_email' in str(e) or 'company_email' in str(e):
                flash('El email de empresa ya está siendo usado por otra empresa.', 'danger')
            else:
                flash('Error al crear la empresa. Verifica que todos los datos sean únicos.', 'danger')
    
    companies = Company.query.filter_by(is_active=True).all()
    return render_template('admin/companies.html', form=form, companies=companies)

@admin.route('/edit_company/<int:company_id>', methods=['GET', 'POST'])
@login_required
@admin_global_required
def edit_company(company_id):
    """Editar empresa existente"""
    company = Company.query.get_or_404(company_id)
    form = CompanyForm(company_id=company.id, obj=company)
    
    if form.validate_on_submit():
        company.name = form.name.data
        company.company_email = form.company_email.data
        company.logo_url = form.logo_url.data if form.logo_url.data else None
        company.primary_color = form.primary_color.data
        company.secondary_color = form.secondary_color.data
        
        try:
            db.session.commit()
            flash(f'¡Empresa "{company.name}" actualizada exitosamente!', 'success')
            return redirect(url_for('admin.manage_companies'))
        except IntegrityError as e:
            db.session.rollback()
            # Verificar si es error de constraint de email único
            if 'uq_company_company_email' in str(e) or 'company_email' in str(e):
                flash('El email de empresa ya está siendo usado por otra empresa.', 'danger')
            else:
                flash('Error al actualizar la empresa. Verifica que todos los datos sean únicos.', 'danger')
    
    # Obtener credenciales del admin para mostrar
    admin_user = User.query.filter_by(company_id=company_id, role='admin_empresa').first()
    return render_template('admin/edit_company.html', form=form, company=company, admin_user=admin_user)

@admin.route('/edit_admin_credentials/<int:company_id>', methods=['GET', 'POST'])
@login_required
@admin_global_required
def edit_admin_credentials(company_id):
    """Editar credenciales del administrador de empresa"""
    company = Company.query.get_or_404(company_id)
    
    # Buscar el administrador de la empresa
    admin_user = User.query.filter_by(company_id=company_id, role='admin_empresa').first()
    if not admin_user:
        flash('No se encontró un administrador para esta empresa.', 'danger')
        return redirect(url_for('admin.manage_companies'))
    
    form = EditAdminCredentialsForm()
    
    # Pre-llenar el formulario con los datos actuales
    if request.method == 'GET':
        form.username.data = admin_user.username
        form.email.data = admin_user.email
    
    if form.validate_on_submit():
        # Verificar si el username ya existe dentro de la misma empresa (excluyendo el usuario actual)
        existing_user = User.query.filter(
            User.username == form.username.data,
            User.company_id == admin_user.company_id,
            User.id != admin_user.id
        ).first()
        if existing_user:
            flash('El nombre de usuario ya está registrado.', 'danger')
            return render_template('admin/edit_admin_credentials.html', form=form, company=company, admin_user=admin_user)
        
        # Verificar si el email ya existe dentro de la misma empresa (excluyendo el usuario actual)
        existing_user = User.query.filter(
            User.email == form.email.data,
            User.company_id == admin_user.company_id,
            User.id != admin_user.id
        ).first()
        if existing_user:
            flash('El correo electrónico ya está registrado.', 'danger')
            return render_template('admin/edit_admin_credentials.html', form=form, company=company, admin_user=admin_user)
        
        # Actualizar credenciales
        admin_user.username = form.username.data
        admin_user.email = form.email.data
        admin_user.set_password(form.password.data)
        
        db.session.commit()
        
        flash(f'¡Credenciales del administrador de "{company.name}" actualizadas exitosamente! Usuario: {admin_user.username}', 'success')
        return redirect(url_for('admin.manage_companies'))
    
    return render_template('admin/edit_admin_credentials.html', form=form, company=company, admin_user=admin_user)

@admin.route('/reset_admin_password/<int:company_id>', methods=['POST'])
@login_required
@admin_global_required
def reset_admin_password(company_id):
    """Resetear contraseña del administrador de empresa a la predeterminada"""
    company = Company.query.get_or_404(company_id)
    
    # Buscar el administrador de la empresa
    admin_user = User.query.filter_by(company_id=company_id, role='admin_empresa').first()
    if not admin_user:
        flash('No se encontró un administrador para esta empresa.', 'danger')
        return redirect(url_for('admin.manage_companies'))
    
    # Generar la contraseña predeterminada 
    default_password = f"{company.name.lower().replace(' ', '')}123"
    admin_user.set_password(default_password)
    
    try:
        db.session.commit()
        flash(f'¡Contraseña del administrador de "{company.name}" reseteada! Usuario: {admin_user.username}, nueva contraseña: {default_password}', 'warning')
    except Exception as e:
        db.session.rollback()
        flash('Error al resetear la contraseña. Inténtalo de nuevo.', 'danger')
    
    return redirect(url_for('admin.manage_companies'))

@admin.route('/users', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_users():
    """Gestión de usuarios"""
    form = UserManagementForm()
    
    if form.validate_on_submit():
        # Validar permisos
        if not current_user.can_manage_users(form.company_id.data):
            flash('No tienes permisos para crear usuarios en esa empresa.', 'danger')
            return render_template('admin/users.html', form=form, users=[])
        
        # Verificar email único dentro de la empresa objetivo
        target_company_id = form.company_id.data
        existing_user = User.query.filter_by(
            email=form.email.data,
            company_id=target_company_id
        ).first()
        
        # También verificar username único dentro de la empresa
        existing_username = User.query.filter_by(
            username=form.username.data,
            company_id=target_company_id
        ).first()
        if existing_user:
            flash('El correo electrónico ya está registrado en esta empresa.', 'danger')
        elif existing_username:
            flash('El nombre de usuario ya existe en esta empresa.', 'danger')
        else:
            user = User(
                username=form.username.data,
                email=form.email.data,
                role=form.role.data,
                company_id=form.company_id.data
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            
            flash(f'¡Usuario "{user.username}" creado exitosamente!', 'success')
            return redirect(url_for('admin.manage_users'))
    
    # Filtrar usuarios según permisos
    if current_user.is_admin_global():
        users = User.query.all()
    else:
        users = User.query.filter_by(company_id=current_user.company_id).all()
    
    return render_template('admin/users.html', form=form, users=users)

@admin.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Eliminar usuario"""
    user = User.query.get_or_404(user_id)
    
    # Validar permisos
    if not current_user.can_manage_users(user.company_id):
        flash('No tienes permisos para eliminar este usuario.', 'danger')
        return redirect(url_for('admin.manage_users'))
    
    # No permitir que se elimine a sí mismo
    if user.id == current_user.id:
        flash('No puedes eliminarte a ti mismo.', 'danger')
        return redirect(url_for('admin.manage_users'))
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    flash(f'Usuario "{username}" eliminado exitosamente.', 'success')
    return redirect(url_for('admin.manage_users'))

@admin.route('/company/<int:company_id>/toggle_status', methods=['POST'])
@login_required
@admin_global_required
def toggle_company_status(company_id):
    """Activar/desactivar empresa"""
    company = Company.query.get_or_404(company_id)
    company.is_active = not company.is_active
    db.session.commit()
    
    status = 'activada' if company.is_active else 'desactivada'
    flash(f'Empresa "{company.name}" {status} exitosamente.', 'success')
    return redirect(url_for('admin.manage_companies'))

@admin.route('/modules', methods=['GET', 'POST'])
@login_required
@admin_global_required
def manage_modules():
    """Gestionar módulos activos por empresa"""
    companies = Company.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        # Verificar si es actualización de preferencias del super admin
        if request.form.get('admin_preferences') == '1':
            # Actualizar preferencias del super admin
            current_user.admin_pref_inventory = 'admin_pref_inventory' in request.form
            current_user.admin_pref_pos = 'admin_pref_pos' in request.form
            current_user.admin_pref_appointments = 'admin_pref_appointments' in request.form
            current_user.admin_pref_portfolio = 'admin_pref_portfolio' in request.form
            current_user.admin_pref_scrum = 'admin_pref_scrum' in request.form
            current_user.admin_pref_notion = 'admin_pref_notion' in request.form
            
            db.session.commit()
            flash('Tus preferencias de módulos han sido actualizadas', 'success')
            return redirect(url_for('admin.manage_modules'))
        else:
            # Actualizar módulos de empresa
            company_id = request.form.get('company_id')
            company = Company.query.get_or_404(company_id)
            
            # Actualizar módulos
            company.module_inventory = 'module_inventory' in request.form
            company.module_pos = 'module_pos' in request.form
            company.module_appointments = 'module_appointments' in request.form
            company.module_portfolio = 'module_portfolio' in request.form
            company.module_scrum = 'module_scrum' in request.form
            company.module_notion = 'module_notion' in request.form
            
            db.session.commit()
            flash(f'Módulos actualizados para {company.name}', 'success')
            return redirect(url_for('admin.manage_modules'))
    
    return render_template('admin/modules.html', companies=companies)