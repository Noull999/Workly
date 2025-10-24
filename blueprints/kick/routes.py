from flask import render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_required, current_user
from . import kick_bp
import os
import secrets
import requests
import hashlib
import base64
from urllib.parse import urlencode

KICK_CLIENT_ID = os.environ.get('KICK_CLIENT_ID')
KICK_CLIENT_SECRET = os.environ.get('KICK_CLIENT_SECRET')
KICK_REDIRECT_URI = None

def get_redirect_uri():
    """Genera la URL de redirección dinámica basada en el dominio actual"""
    global KICK_REDIRECT_URI
    if KICK_REDIRECT_URI is None:
        if 'REPLIT_DEV_DOMAIN' in os.environ:
            domain = os.environ['REPLIT_DEV_DOMAIN']
            KICK_REDIRECT_URI = f"https://{domain}/kick/callback"
        else:
            KICK_REDIRECT_URI = "http://localhost:5000/kick/callback"
    return KICK_REDIRECT_URI

def generate_code_verifier():
    """Genera un code_verifier aleatorio para PKCE (43-128 caracteres)"""
    return secrets.token_urlsafe(64)

def generate_code_challenge(code_verifier):
    """Genera un code_challenge a partir del code_verifier usando SHA256"""
    digest = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    challenge = base64.urlsafe_b64encode(digest).decode('utf-8').rstrip('=')
    return challenge

@kick_bp.route('/login')
def login():
    """Inicia el flujo OAuth de Kick con PKCE"""
    state = secrets.token_urlsafe(32)
    session['kick_oauth_state'] = state
    
    # Generar PKCE
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    session['kick_code_verifier'] = code_verifier
    
    if 'return_to' in request.args:
        session['kick_return_to'] = request.args.get('return_to')
    
    params = {
        'client_id': KICK_CLIENT_ID,
        'redirect_uri': get_redirect_uri(),
        'response_type': 'code',
        'state': state,
        'scope': 'user:read channel:read',
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256'
    }
    
    auth_url = f"https://id.kick.com/oauth/authorize?{urlencode(params)}"
    return redirect(auth_url)

@kick_bp.route('/callback')
def callback():
    """Callback OAuth de Kick"""
    try:
        state = request.args.get('state')
        code = request.args.get('code')
        
        if not state or state != session.get('kick_oauth_state'):
            flash('Error de validación OAuth. Intenta de nuevo.', 'danger')
            return redirect(url_for('dashboard'))
        
        if not code:
            flash('Error en la autorización de Kick.', 'danger')
            return redirect(url_for('dashboard'))
        
        # Recuperar code_verifier de la sesión para PKCE
        code_verifier = session.get('kick_code_verifier')
        if not code_verifier:
            flash('Error: sesión OAuth inválida.', 'danger')
            return redirect(url_for('dashboard'))
        
        token_data = {
            'grant_type': 'authorization_code',
            'client_id': KICK_CLIENT_ID,
            'client_secret': KICK_CLIENT_SECRET,
            'redirect_uri': get_redirect_uri(),
            'code': code,
            'code_verifier': code_verifier
        }
        
        token_response = requests.post(
            'https://id.kick.com/oauth/token',
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        
        if token_response.status_code != 200:
            flash('Error al obtener el token de acceso de Kick.', 'danger')
            return redirect(url_for('dashboard'))
        
        token_info = token_response.json()
        access_token = token_info.get('access_token')
        refresh_token = token_info.get('refresh_token')
        
        user_response = requests.get(
            'https://kick.com/api/v2/user',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        
        if user_response.status_code != 200:
            flash('Error al obtener información del usuario de Kick.', 'danger')
            return redirect(url_for('dashboard'))
        
        kick_user_data = user_response.json()
        
        from models import KickUser
        from app import db
        
        kick_user = KickUser.query.filter_by(kick_id=kick_user_data['id']).first()
        
        if not kick_user:
            kick_user = KickUser()
            kick_user.kick_id = kick_user_data['id']
        
        kick_user.username = kick_user_data.get('username')
        kick_user.email = kick_user_data.get('email')
        kick_user.access_token = access_token
        kick_user.refresh_token = refresh_token
        
        db.session.add(kick_user)
        db.session.commit()
        
        session['kick_user_id'] = kick_user.id
        session['kick_username'] = kick_user.username
        
        flash(f'¡Conectado exitosamente como {kick_user.username}!', 'success')
        
        return_to = session.pop('kick_return_to', url_for('dashboard'))
        return redirect(return_to)
        
    except Exception as e:
        flash(f'Error en el proceso de autenticación: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        session.pop('kick_oauth_state', None)
        session.pop('kick_code_verifier', None)

@kick_bp.route('/logout')
def logout():
    """Cierra sesión de Kick"""
    session.pop('kick_user_id', None)
    session.pop('kick_username', None)
    flash('Sesión de Kick cerrada.', 'info')
    
    return_to = request.args.get('return_to', url_for('dashboard'))
    return redirect(return_to)

@kick_bp.route('/user-points/<channel_username>')
def user_points(channel_username):
    """Obtiene los puntos de lealtad del usuario autenticado en un canal específico"""
    if 'kick_user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    try:
        from models import KickUser
        kick_user = KickUser.query.get(session['kick_user_id'])
        
        if not kick_user:
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        headers = {'Authorization': f'Bearer {kick_user.access_token}'}
        response = requests.get(
            f'https://kick.com/api/v1/channels/{channel_username}/users/{kick_user.kick_id}/loyalty',
            headers=headers
        )
        
        if response.status_code == 200:
            loyalty_data = response.json()
            return jsonify({
                'points': loyalty_data.get('points', 0),
                'username': kick_user.username
            })
        else:
            return jsonify({'error': 'No se pudieron obtener los puntos'}), response.status_code
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@kick_bp.route('/raffle/<int:raffle_id>/enter', methods=['POST'])
def enter_raffle(raffle_id):
    """Participar en un sorteo usando puntos de Kick"""
    if 'kick_user_id' not in session:
        flash('Debes iniciar sesión con Kick para participar en sorteos.', 'warning')
        return redirect(request.referrer or url_for('public.yanglee_page'))
    
    try:
        from models import Raffle, RaffleEntry, KickUser
        from app import db
        
        kick_user = KickUser.query.get(session['kick_user_id'])
        if not kick_user:
            flash('Usuario de Kick no encontrado.', 'danger')
            return redirect(request.referrer or url_for('public.yanglee_page'))
        
        raffle = Raffle.query.get_or_404(raffle_id)
        
        # Verificar que el sorteo esté activo
        if not raffle.is_active:
            flash('Este sorteo ya no está activo.', 'warning')
            return redirect(request.referrer or url_for('public.yanglee_page'))
        
        # Verificar si ya participó
        existing_entry = RaffleEntry.query.filter_by(
            raffle_id=raffle_id,
            kick_user_id=kick_user.id
        ).first()
        
        if existing_entry:
            flash('Ya estás participando en este sorteo.', 'info')
            return redirect(request.referrer or url_for('public.yanglee_page'))
        
        # Verificar puntos del usuario
        headers = {'Authorization': f'Bearer {kick_user.access_token}'}
        response = requests.get(
            f'https://kick.com/api/v1/channels/{raffle.kick_channel_username}/users/{kick_user.kick_id}/loyalty',
            headers=headers
        )
        
        if response.status_code != 200:
            flash('No se pudieron verificar tus puntos de Kick.', 'danger')
            return redirect(request.referrer or url_for('public.yanglee_page'))
        
        loyalty_data = response.json()
        user_points = loyalty_data.get('points', 0)
        
        # Verificar si tiene suficientes puntos
        if user_points < raffle.entry_cost:
            flash(f'No tienes suficientes puntos. Necesitas {raffle.entry_cost} puntos pero solo tienes {user_points}.', 'danger')
            return redirect(request.referrer or url_for('public.yanglee_page'))
        
        # Crear entrada de sorteo
        entry_number = raffle.entry_count + 1
        entry = RaffleEntry(
            raffle_id=raffle_id,
            kick_user_id=kick_user.id,
            points_spent=raffle.entry_cost,
            entry_number=entry_number
        )
        
        db.session.add(entry)
        db.session.commit()
        
        flash(f'¡Participación registrada! Tu número de entrada es #{entry_number}. Puntos gastados: {raffle.entry_cost}', 'success')
        return redirect(request.referrer or url_for('public.yanglee_page'))
        
    except Exception as e:
        flash(f'Error al participar en el sorteo: {str(e)}', 'danger')
        return redirect(request.referrer or url_for('public.yanglee_page'))


# ===== ADMIN ROUTES =====

@kick_bp.route('/admin/raffles')
@login_required
def admin_raffles():
    """Panel de administración de sorteos"""
    from flask_login import current_user
    from models import Raffle
    
    # Sorteos del usuario actual
    raffles = Raffle.query.filter_by(user_id=current_user.id).order_by(Raffle.created_at.desc()).all()
    
    return render_template('kick/admin_raffles.html', raffles=raffles)

@kick_bp.route('/admin/raffles/create', methods=['GET', 'POST'])
@login_required
def create_raffle():
    """Crear un nuevo sorteo"""
    from flask_login import current_user
    from forms import RaffleForm
    from models import Raffle
    from app import db
    import json
    
    form = RaffleForm()
    
    # Leer kick_username del JSON del usuario
    kick_username = None
    try:
        import os
        json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'user_data.json')
        with open(json_path, 'r', encoding='utf-8') as f:
            usuarios = json.load(f)
        for user in usuarios:
            if user.get('email', '').lower() == current_user.email.lower():
                kick_username = user.get('kick_username')
                break
    except:
        pass
    
    if not kick_username:
        flash('Tu cuenta no tiene un canal de Kick configurado.', 'danger')
        return redirect(url_for('kick.admin_raffles'))
    
    if form.validate_on_submit():
        raffle = Raffle(
            title=form.title.data,
            description=form.description.data,
            prize=form.prize.data,
            entry_cost=form.entry_cost.data,
            max_entries=form.max_entries.data if form.max_entries.data else None,
            user_id=current_user.id,
            kick_channel_username=kick_username,
            end_date=form.end_date.data if form.end_date.data else None
        )
        
        db.session.add(raffle)
        db.session.commit()
        
        flash(f'Sorteo "{raffle.title}" creado exitosamente.', 'success')
        return redirect(url_for('kick.admin_raffles'))
    
    return render_template('kick/create_raffle.html', form=form)

@kick_bp.route('/admin/raffles/<int:raffle_id>/draw-winner', methods=['POST'])
@login_required
def draw_winner(raffle_id):
    """Seleccionar ganador aleatorio de un sorteo"""
    from flask_login import current_user
    from models import Raffle, RaffleEntry
    from app import db
    from datetime import datetime
    import random
    
    raffle = Raffle.query.get_or_404(raffle_id)
    
    # Verificar que el sorteo pertenece al usuario
    if raffle.user_id != current_user.id:
        flash('No tienes permiso para gestionar este sorteo.', 'danger')
        return redirect(url_for('kick.admin_raffles'))
    
    # Verificar que el sorteo está activo
    if raffle.status != 'active':
        flash('Este sorteo ya no está activo.', 'warning')
        return redirect(url_for('kick.admin_raffles'))
    
    # Verificar que hay participantes
    if raffle.entry_count == 0:
        flash('No hay participantes en este sorteo.', 'warning')
        return redirect(url_for('kick.admin_raffles'))
    
    # Seleccionar ganador aleatorio
    entries = raffle.entries
    winner_entry = random.choice(entries)
    
    # Actualizar sorteo
    raffle.winner_kick_user_id = winner_entry.kick_user_id
    raffle.status = 'completed'
    raffle.completed_at = datetime.utcnow()
    
    db.session.commit()
    
    flash(f'¡Ganador seleccionado! 🎉 Usuario: {winner_entry.kick_user.username} (Entrada #{winner_entry.entry_number})', 'success')
    return redirect(url_for('kick.admin_raffles'))

@kick_bp.route('/admin/raffles/<int:raffle_id>/cancel', methods=['POST'])
@login_required
def cancel_raffle(raffle_id):
    """Cancelar un sorteo"""
    from flask_login import current_user
    from models import Raffle
    from app import db
    
    raffle = Raffle.query.get_or_404(raffle_id)
    
    # Verificar que el sorteo pertenece al usuario
    if raffle.user_id != current_user.id:
        flash('No tienes permiso para gestionar este sorteo.', 'danger')
        return redirect(url_for('kick.admin_raffles'))
    
    raffle.status = 'cancelled'
    db.session.commit()
    
    flash(f'Sorteo "{raffle.title}" cancelado.', 'info')
    return redirect(url_for('kick.admin_raffles'))
