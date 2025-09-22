"""
Common decorators and utilities for blueprints
"""
from functools import wraps
from flask import flash, redirect, url_for, render_template
from flask_login import current_user

def admin_global_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin_global():
            flash('Acceso denegado. Se requieren permisos de administrador global.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or (not current_user.is_admin_global() and not current_user.is_admin_empresa()):
            flash('Acceso denegado. Se requieren permisos de administrador.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def module_required(module_name):
    """Decorator to check if a module is active for the current company"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            
            # Super admin tiene acceso a todos los módulos
            if current_user.is_admin_global():
                return f(*args, **kwargs)
            
            company = current_user.company
            module_active = getattr(company, f'module_{module_name}', False)
            
            if not module_active:
                return render_template('errors/module_disabled.html', module_name=module_name), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator