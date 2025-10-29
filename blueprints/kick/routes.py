from flask import render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_required, current_user, login_user
from . import kick_bp
import os
import secrets
import requests
import hashlib
import base64
from urllib.parse import urlencode
from time import time

# Cache temporal en memoria para PKCE (soluciona problemas de sesión en Replit)
_temp_oauth_cache = {}

KICK_CLIENT_ID = os.environ.get('KICK_CLIENT_ID')
KICK_CLIENT_SECRET = os.environ.get('KICK_CLIENT_SECRET')
KICK_REDIRECT_URI = None

def get_redirect_uri():
    """Genera la URL de redirección dinámica basada en el dominio actual"""
    global KICK_REDIRECT_URI
    if KICK_REDIRECT_URI is None:
        # Priorizar variable de entorno KICK_REDIRECT_URI
        env_redirect = os.getenv("KICK_REDIRECT_URI")
        if env_redirect:
            KICK_REDIRECT_URI = env_redirect
        elif 'REPLIT_DEV_DOMAIN' in os.environ:
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
    import logging
    logger = logging.getLogger(__name__)
    
    # Hacer la sesión permanente para que persista durante OAuth
    session.permanent = True
    
    state = secrets.token_urlsafe(32)
    
    # Generar PKCE
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    
    # GUARDAR EN CACHE EN MEMORIA en vez de session (soluciona problema de Replit)
    _temp_oauth_cache[state] = {
        "verifier": code_verifier,
        "timestamp": time()
    }
    
    redirect_uri = get_redirect_uri()
    
    logger.debug(f"[KICK LOGIN] State generado: {state[:10]}...")
    logger.debug(f"[KICK LOGIN] Code verifier guardado en CACHE: {code_verifier[:10]}...")
    logger.debug(f"[KICK LOGIN] Code challenge: {code_challenge[:10]}...")
    logger.debug(f"[KICK LOGIN] Redirect URI: {redirect_uri}")
    logger.debug(f"[KICK LOGIN] Cache size: {len(_temp_oauth_cache)} entries")
    
    if 'return_to' in request.args:
        session['kick_return_to'] = request.args.get('return_to')
    
    params = {
        'client_id': KICK_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'state': state,
        'scope': 'user:read channel:read',
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256'
    }
    
    auth_url = f"https://id.kick.com/oauth/authorize?{urlencode(params)}"
    logger.debug(f"[KICK LOGIN] Redirigiendo a: {auth_url[:80]}...")
    return redirect(auth_url)

@kick_bp.route('/callback')
def callback():
    """Callback OAuth de Kick"""
    import logging
    logger = logging.getLogger(__name__)
    
    # LOGGING CRÍTICO: Esto debe aparecer SIEMPRE
    print("=" * 80)
    print("[KICK CALLBACK] ¡¡¡CALLBACK EJECUTADO!!!")
    print(f"[KICK CALLBACK] REQUEST URL: {request.url}")
    print(f"[KICK CALLBACK] REQUEST ARGS: {dict(request.args)}")
    print(f"[KICK CALLBACK] REQUEST METHOD: {request.method}")
    print(f"[KICK CALLBACK] SESSION KEYS: {list(session.keys())}")
    print("=" * 80)
    
    logger.info("="*80)
    logger.info("[KICK CALLBACK] ¡¡¡CALLBACK EJECUTADO!!!")
    logger.info(f"[KICK CALLBACK] REQUEST URL: {request.url}")
    logger.info(f"[KICK CALLBACK] REQUEST ARGS: {dict(request.args)}")
    logger.info(f"[KICK CALLBACK] SESSION KEYS: {list(session.keys())}")
    logger.info("="*80)
    
    try:
        # Verificar si Kick envió un error
        error = request.args.get('error')
        error_description = request.args.get('error_description', '')
        
        if error:
            logger.error(f"[KICK CALLBACK] Kick rechazó la autorización: {error} - {error_description}")
            flash(f'Autorización de Kick cancelada o rechazada.', 'warning')
            return redirect(url_for('public.yanglee_page'))
        
        state = request.args.get('state')
        code = request.args.get('code')
        
        logger.debug(f"[KICK CALLBACK] State recibido: {state[:10] if state else 'None'}...")
        logger.debug(f"[KICK CALLBACK] Code recibido: {code[:10] if code else 'None'}...")
        logger.debug(f"[KICK CALLBACK] Cache size: {len(_temp_oauth_cache)} entries")
        
        if not state:
            logger.error(f"[KICK CALLBACK] Error: no se recibió state")
            flash('Error de validación OAuth. Intenta de nuevo.', 'danger')
            return redirect(url_for('public.yanglee_page'))
        
        if not code:
            logger.error(f"[KICK CALLBACK] Error: no se recibió código de autorización")
            flash('Error en la autorización de Kick.', 'danger')
            return redirect(url_for('public.yanglee_page'))
        
        # Recuperar code_verifier del CACHE EN MEMORIA en vez de sesión
        code_verifier = None
        if state in _temp_oauth_cache:
            code_verifier = _temp_oauth_cache[state]["verifier"]
            logger.debug(f"[KICK CALLBACK] Code verifier recuperado de CACHE: {code_verifier[:10]}...")
            # Limpiar el cache después de usar (one-time use)
            _temp_oauth_cache.pop(state, None)
        else:
            logger.error(f"[KICK CALLBACK] Error: state no encontrado en cache")
            logger.error(f"[KICK CALLBACK] Cache size: {len(_temp_oauth_cache)} entries")
            flash('Error: sesión OAuth expirada o inválida. Intenta de nuevo.', 'danger')
            return redirect(url_for('public.yanglee_page'))
        
        token_data = {
            'grant_type': 'authorization_code',
            'client_id': KICK_CLIENT_ID,
            'client_secret': KICK_CLIENT_SECRET,
            'redirect_uri': get_redirect_uri(),
            'code': code,
            'code_verifier': code_verifier
        }
        
        logger.debug(f"[KICK CALLBACK] Intercambiando código por token...")
        
        token_response = requests.post(
            'https://id.kick.com/oauth/token',
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        
        logger.debug(f"[KICK CALLBACK] Token response status: {token_response.status_code}")
        
        if token_response.status_code != 200:
            logger.error(f"[KICK CALLBACK] Error al obtener token: {token_response.text}")
            error_msg = token_response.json().get('error_description', 'No se pudo obtener token') if token_response.headers.get('content-type', '').startswith('application/json') else 'No se pudo obtener token'
            flash(f'Error OAuth: {error_msg}', 'danger')
            return redirect(url_for('public.yanglee_page'))
        
        token_info = token_response.json()
        access_token = token_info.get('access_token')
        refresh_token = token_info.get('refresh_token')
        
        logger.debug(f"[KICK CALLBACK] Token obtenido exitosamente")
        
        user_response = requests.get(
            'https://kick.com/api/v1/user',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        
        if user_response.status_code != 200:
            flash('Error al obtener información del usuario de Kick.', 'danger')
            return redirect(url_for('public.yanglee_page'))
        
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
        
        # Autenticar al usuario con Flask-Login
        login_user(kick_user)
        session['kick_username'] = kick_user.username
        
        flash(f'¡Conectado exitosamente como {kick_user.username}!', 'success')
        
        return_to = session.pop('kick_return_to', url_for('public.yanglee_page'))
        return redirect(return_to)
        
    except Exception as e:
        flash(f'Error en el proceso de autenticación: {str(e)}', 'danger')
        return redirect(url_for('public.yanglee_page'))
    finally:
        session.pop('kick_oauth_state', None)
        session.pop('kick_code_verifier', None)

@kick_bp.route('/logout')
def logout():
    """Cierra sesión de Kick"""
    from flask_login import logout_user
    logout_user()
    session.pop('kick_username', None)
    flash('Sesión de Kick cerrada.', 'info')
    
    return_to = request.args.get('return_to', url_for('dashboard'))
    return redirect(return_to)

@kick_bp.route('/user-points/<channel_username>')
def user_points(channel_username):
    """Obtiene los puntos de lealtad del usuario autenticado en un canal específico"""
    from models import KickUser
    
    # Verificar que el usuario esté autenticado y sea un KickUser
    if not current_user.is_authenticated:
        return jsonify({'error': 'No autenticado'}), 401
    
    try:
        # Verificar que current_user sea un KickUser
        if not isinstance(current_user._get_current_object(), KickUser):
            return jsonify({'error': 'Debes autenticarte con Kick'}), 401
        
        kick_user = current_user._get_current_object()
        
        if not kick_user or not kick_user.access_token:
            return jsonify({'error': 'Usuario no encontrado o token inválido'}), 404
        
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
        elif response.status_code == 401:
            return jsonify({'error': 'Token expirado. Conecta de nuevo tu cuenta de Kick.'}), 401
        else:
            return jsonify({'error': 'No se pudieron obtener los puntos'}), response.status_code
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@kick_bp.route('/raffle/<int:raffle_id>/enter', methods=['POST'])
def enter_raffle(raffle_id):
    """Participar en un sorteo usando puntos de Kick"""
    from models import Raffle, RaffleEntry, KickUser
    from app import db
    
    # Verificar que el usuario esté autenticado y sea un KickUser
    if not current_user.is_authenticated:
        flash('Debes iniciar sesión con Kick para participar en sorteos.', 'warning')
        return redirect(request.referrer or url_for('public.yanglee_page'))
    
    if not isinstance(current_user._get_current_object(), KickUser):
        flash('Debes autenticarte con Kick para participar en sorteos.', 'warning')
        return redirect(request.referrer or url_for('public.yanglee_page'))
    
    try:
        kick_user = current_user._get_current_object()
        
        if not kick_user or not kick_user.access_token:
            flash('Usuario de Kick no encontrado o token inválido.', 'danger')
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

@kick_bp.route('/admin/raffles/<int:raffle_id>/delete', methods=['POST'])
@login_required
def delete_raffle(raffle_id):
    """Eliminar permanentemente un sorteo"""
    from flask_login import current_user
    from models import Raffle
    from app import db
    
    raffle = Raffle.query.get_or_404(raffle_id)
    
    # Verificar que el sorteo pertenece al usuario
    if raffle.user_id != current_user.id:
        flash('No tienes permiso para gestionar este sorteo.', 'danger')
        return redirect(url_for('kick.admin_raffles'))
    
    # Guardar título para el mensaje
    titulo = raffle.title
    
    # Eliminar sorteo y sus entradas (CASCADE debería manejar esto)
    db.session.delete(raffle)
    db.session.commit()
    
    flash(f'Sorteo "{titulo}" eliminado permanentemente.', 'success')
    return redirect(url_for('kick.admin_raffles'))

@kick_bp.route('/admin/raffles/<int:raffle_id>/finalize', methods=['POST'])
@login_required
def finalize_raffle(raffle_id):
    """Finalizar un sorteo sin seleccionar ganador"""
    from flask_login import current_user
    from models import Raffle
    from app import db
    from datetime import datetime
    
    raffle = Raffle.query.get_or_404(raffle_id)
    
    # Verificar que el sorteo pertenece al usuario
    if raffle.user_id != current_user.id:
        flash('No tienes permiso para gestionar este sorteo.', 'danger')
        return redirect(url_for('kick.admin_raffles'))
    
    # Verificar que el sorteo está activo
    if raffle.status != 'active':
        flash('Este sorteo ya no está activo.', 'warning')
        return redirect(url_for('kick.admin_raffles'))
    
    # Finalizar sorteo sin ganador
    raffle.status = 'completed'
    raffle.completed_at = datetime.utcnow()
    
    db.session.commit()
    
    flash(f'Sorteo "{raffle.title}" finalizado sin ganador.', 'info')
    return redirect(url_for('kick.admin_raffles'))

@kick_bp.route('/admin/raffles/<int:raffle_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_raffle(raffle_id):
    """Editar un sorteo existente"""
    from flask_login import current_user
    from forms import RaffleForm
    from models import Raffle
    from app import db
    
    raffle = Raffle.query.get_or_404(raffle_id)
    
    # Verificar que el sorteo pertenece al usuario
    if raffle.user_id != current_user.id:
        flash('No tienes permiso para gestionar este sorteo.', 'danger')
        return redirect(url_for('kick.admin_raffles'))
    
    form = RaffleForm(obj=raffle)
    
    if form.validate_on_submit():
        raffle.title = form.title.data
        raffle.description = form.description.data
        raffle.prize = form.prize.data
        raffle.entry_cost = form.entry_cost.data
        raffle.max_entries = form.max_entries.data if form.max_entries.data else None
        raffle.end_date = form.end_date.data if form.end_date.data else None
        
        db.session.commit()
        
        flash(f'Sorteo "{raffle.title}" actualizado exitosamente.', 'success')
        return redirect(url_for('kick.admin_raffles'))
    
    return render_template('kick/edit_raffle.html', form=form, raffle=raffle)
