from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from . import auth
from models import User
from forms import LoginForm

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        # Permitir login con username o email
        username_or_email = form.username.data
        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            next_page = request.args.get('next')
            flash(f'¡Bienvenido de nuevo, {user.username}!', 'success')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        flash('Usuario o contraseña inválidos', 'danger')
    
    return render_template('login.html', form=form)

@auth.route('/register')
def register():
    """Página informativa sobre cómo obtener acceso al sistema"""
    return render_template('access_info.html')

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Has cerrado sesión exitosamente.', 'info')
    return redirect(url_for('index'))