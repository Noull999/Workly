from flask import render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_required, current_user, login_user
from . import kick_bp
from app import csrf
import os
import secrets
import requests
import hashlib
import base64
import json
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
    
    # Generar CSRF token
    csrf_token = secrets.token_urlsafe(32)
    
    # Generar PKCE
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    
    # Obtener return_to de request.args, request.referrer, o default
    return_to = request.args.get('return_to') or request.referrer or url_for('public.yanglee_page')
    
    # Codificar state con {csrf, return_to} en JSON+base64
    state_data = {
        "csrf": csrf_token,
        "return_to": return_to
    }
    state_encoded = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()
    
    # GUARDAR EN CACHE EN MEMORIA con el csrf_token como clave
    _temp_oauth_cache[csrf_token] = {
        "verifier": code_verifier,
        "timestamp": time()
    }
    
    redirect_uri = get_redirect_uri()
    
    logger.debug(f"[KICK LOGIN] CSRF token generado: {csrf_token[:10]}...")
    logger.debug(f"[KICK LOGIN] Return to: {return_to}")
    logger.debug(f"[KICK LOGIN] State encoded: {state_encoded[:30]}...")
    logger.debug(f"[KICK LOGIN] Code verifier guardado en CACHE: {code_verifier[:10]}...")
    logger.debug(f"[KICK LOGIN] Code challenge: {code_challenge[:10]}...")
    logger.debug(f"[KICK LOGIN] Redirect URI: {redirect_uri}")
    logger.debug(f"[KICK LOGIN] Cache size: {len(_temp_oauth_cache)} entries")
    
    params = {
        'client_id': KICK_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'state': state_encoded,
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
        
        state_encoded = request.args.get('state')
        code = request.args.get('code')
        
        logger.debug(f"[KICK CALLBACK] State encoded recibido: {state_encoded[:30] if state_encoded else 'None'}...")
        logger.debug(f"[KICK CALLBACK] Code recibido: {code[:10] if code else 'None'}...")
        logger.debug(f"[KICK CALLBACK] Cache size: {len(_temp_oauth_cache)} entries")
        
        if not state_encoded:
            logger.error(f"[KICK CALLBACK] Error: no se recibió state")
            flash('Error de validación OAuth. Intenta de nuevo.', 'danger')
            return redirect(url_for('public.yanglee_page'))
        
        if not code:
            logger.error(f"[KICK CALLBACK] Error: no se recibió código de autorización")
            flash('Error en la autorización de Kick.', 'danger')
            return redirect(url_for('public.yanglee_page'))
        
        # Decodificar state de base64 + JSON
        try:
            # Calcular padding correcto para base64
            padding = -len(state_encoded) % 4
            state_decoded = json.loads(base64.urlsafe_b64decode(state_encoded + "=" * padding).decode())
            csrf_token = state_decoded.get("csrf")
            return_to = state_decoded.get("return_to", url_for('public.yanglee_page'))
            logger.debug(f"[KICK CALLBACK] State decodificado exitosamente")
            logger.debug(f"[KICK CALLBACK] CSRF token: {csrf_token[:10]}...")
            logger.debug(f"[KICK CALLBACK] Return to: {return_to}")
        except Exception as e:
            logger.error(f"[KICK CALLBACK] Error decodificando state: {str(e)}")
            flash('Error de validación OAuth. Intenta de nuevo.', 'danger')
            return redirect(url_for('public.yanglee_page'))
        
        # Recuperar code_verifier del CACHE usando csrf_token
        code_verifier = None
        if csrf_token and csrf_token in _temp_oauth_cache:
            code_verifier = _temp_oauth_cache[csrf_token]["verifier"]
            logger.debug(f"[KICK CALLBACK] Code verifier recuperado de CACHE: {code_verifier[:10]}...")
            # Limpiar el cache después de usar (one-time use)
            _temp_oauth_cache.pop(csrf_token, None)
        else:
            logger.error(f"[KICK CALLBACK] Error: CSRF token no encontrado en cache")
            logger.error(f"[KICK CALLBACK] Cache size: {len(_temp_oauth_cache)} entries")
            flash('Error: sesión OAuth expirada o inválida. Intenta de nuevo.', 'danger')
            return redirect(url_for('public.yanglee_page'))
        
        # DEBUG: Información crítica antes de intercambiar por token
        print("=" * 80)
        print("=== DEBUG CALLBACK ===")
        print(f"Code: {code}")
        print(f"Redirect URI: {get_redirect_uri()}")
        print(f"Verifier: {code_verifier}")
        print(f"CSRF Token: {csrf_token}")
        print(f"Return to: {return_to}")
        print("=" * 80)
        
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
        
        # DEBUG: Respuesta del servidor de tokens
        print("=" * 80)
        print(f"Token status: {token_response.status_code}")
        print(f"Token text: {token_response.text}")
        print("=" * 80)
        
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
        
        # return_to ya fue extraído del state decodificado al inicio
        logger.debug(f"[KICK CALLBACK] Redirigiendo a: {return_to}")
        return redirect(return_to)
        
    except Exception as e:
        logger.error(f"[KICK CALLBACK] Exception: {str(e)}")
        flash(f'Error en el proceso de autenticación: {str(e)}', 'danger')
        # En caso de error, intentar usar return_to si está disponible
        fallback_url = locals().get('return_to', url_for('public.yanglee_page'))
        return redirect(fallback_url)

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
            kick_channel_username=kick_username
        )
        
        db.session.add(raffle)
        db.session.commit()
        
        flash(f'Sorteo "{raffle.title}" creado exitosamente.', 'success')
        return redirect(url_for('kick.admin_raffles'))
    
    return render_template('kick/create_raffle.html', form=form)

@kick_bp.route('/admin/raffles/<int:raffle_id>/draw', methods=['GET'])
@login_required
def raffle_draw_view(raffle_id):
    """Ver sorteo y participantes"""
    from flask_login import current_user
    from models import Raffle
    
    raffle = Raffle.query.get_or_404(raffle_id)
    
    # Verificar que el sorteo pertenece al usuario
    if raffle.user_id != current_user.id:
        flash('No tienes permiso para gestionar este sorteo.', 'danger')
        return redirect(url_for('kick.admin_raffles'))
    
    return render_template('kick/raffle_draw.html', raffle=raffle)

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
    if not raffle.is_active:
        flash('Este sorteo ya no está activo.', 'warning')
        return redirect(url_for('kick.raffle_draw_view', raffle_id=raffle_id))
    
    # Verificar que hay participantes
    if raffle.entry_count == 0:
        flash('No hay participantes en este sorteo.', 'warning')
        return redirect(url_for('kick.raffle_draw_view', raffle_id=raffle_id))
    
    # Seleccionar ganador aleatorio
    entries = raffle.entries
    winner_entry = random.choice(entries)
    
    # Actualizar sorteo
    raffle.winner_viewer_id = winner_entry.viewer_id
    raffle.is_active = False
    
    db.session.commit()
    
    # Redirigir a la página de sorteo con el ganador para mostrar animación
    return redirect(url_for('kick.raffle_draw_view', raffle_id=raffle_id, winner=winner_entry.viewer.username_kick))

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
    
    raffle.is_active = False
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
    if not raffle.is_active:
        flash('Este sorteo ya no está activo.', 'warning')
        return redirect(url_for('kick.admin_raffles'))
    
    # Finalizar sorteo sin ganador
    raffle.is_active = False
    
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
        
        db.session.commit()
        
        flash(f'Sorteo "{raffle.title}" actualizado exitosamente.', 'success')
        return redirect(url_for('kick.admin_raffles'))
    
    return render_template('kick/edit_raffle.html', form=form, raffle=raffle)


# ===== API ENDPOINTS PARA SISTEMA DE PUNTOS SIN OAUTH =====

@kick_bp.route('/api/watchtime/update', methods=['POST'])
@csrf.exempt
def update_watchtime():
    """API: Actualiza watch time y suma puntos cuando el usuario ve el stream en vivo"""
    from models import Viewer, PointsConfig
    from app import db
    from datetime import datetime, timedelta
    from helpers.kick_api import get_stream_status
    
    try:
        data = request.json
        username_kick = data.get('username_kick')
        channel_name = data.get('channel_name')
        
        if not username_kick or not channel_name:
            return jsonify({'ok': False, 'message': 'Username y channel_name son requeridos'}), 400
        
        # Obtener configuración de puntos
        # Uso público sin company - usa None
        config = PointsConfig.query.filter_by(company_id=None).with_for_update().first()
        if not config:
            config = PointsConfig(company_id=None)
            db.session.add(config)
            db.session.flush()
        
        # Verificar si el sistema de puntos está habilitado
        if not config.enabled:
            return jsonify({'ok': False, 'message': 'Sistema de puntos desactivado'}), 403
        
        # Verificar si el canal está en vivo (sin cache para verificación en tiempo real)
        stream_status = get_stream_status(channel_name, use_cache=False)
        if not stream_status.get('is_live'):
            return jsonify({'ok': False, 'message': 'Canal offline'}), 200
        
        # Buscar o crear viewer con SELECT ... FOR UPDATE para prevenir race conditions
        viewer = Viewer.query.filter_by(username_kick=username_kick).with_for_update().first()
        
        if not viewer:
            # Nuevo viewer - crear y permitir primera asignación de puntos
            viewer = Viewer(
                username_kick=username_kick, 
                points=config.points_per_minute_watching, 
                watch_time=1, 
                messages_sent=0, 
                last_seen=datetime.utcnow()
            )
            db.session.add(viewer)
            db.session.commit()
            return jsonify({'ok': True, 'points': viewer.points, 'watch_time': viewer.watch_time})
        
        # COOLDOWN: Verificar cooldown configurable
        if viewer.last_seen:
            time_since_last = datetime.utcnow() - viewer.last_seen
            if time_since_last < timedelta(seconds=config.cooldown_seconds):
                # Cooldown activo - no permitir farming de puntos
                seconds_remaining = int(config.cooldown_seconds - time_since_last.total_seconds())
                db.session.commit()  # Liberar lock
                return jsonify({
                    'ok': False,
                    'message': f'Espera {seconds_remaining}s antes de la próxima actualización',
                    'points': viewer.points,
                    'watch_time': viewer.watch_time
                }), 429  # Too Many Requests
        
        # TODO: Implementar max_points_per_day cuando se agregue daily_points tracking a Viewer model
        # Por ahora el límite diario no se enforces (requiere campos adicionales en DB)
        
        # Sumar puntos y tiempo (fila bloqueada - seguro contra concurrencia)
        viewer.points += config.points_per_minute_watching
        viewer.watch_time += 1
        viewer.last_seen = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({'ok': True, 'points': viewer.points, 'watch_time': viewer.watch_time})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'message': str(e)}), 500


@kick_bp.route('/api/raffle/join', methods=['POST'])
@csrf.exempt
def join_raffle():
    """API: Permitir que un usuario se una a un sorteo gastando puntos"""
    from models import Viewer, Raffle, RaffleEntry
    from app import db
    
    try:
        data = request.json
        username_kick = data.get('username_kick')
        raffle_id = data.get('raffle_id')
        
        if not username_kick or not raffle_id:
            return jsonify({'ok': False, 'message': 'Username y raffle_id son requeridos'}), 400
        
        # Buscar viewer
        viewer = Viewer.query.filter_by(username_kick=username_kick).first()
        if not viewer:
            return jsonify({'ok': False, 'message': 'Usuario no encontrado'}), 404
        
        # Buscar raffle
        raffle = Raffle.query.get(raffle_id)
        if not raffle or not raffle.is_active:
            return jsonify({'ok': False, 'message': 'Error al unirse'}), 404
        
        # Verificar si ya participó
        existing_entry = RaffleEntry.query.filter_by(raffle_id=raffle_id, viewer_id=viewer.id).first()
        if existing_entry:
            return jsonify({'ok': False, 'message': 'Ya participaste en este sorteo'}), 400
        
        # Verificar puntos suficientes
        if viewer.points < raffle.entry_cost:
            return jsonify({'ok': False, 'message': 'Puntos insuficientes'}), 400
        
        # Restar puntos y crear entrada
        viewer.points -= raffle.entry_cost
        
        # Calcular número de entrada
        entry_number = raffle.entry_count + 1
        
        entry = RaffleEntry(raffle_id=raffle_id, viewer_id=viewer.id, entry_number=entry_number)
        db.session.add(entry)
        
        # Incrementar entry_count del sorteo
        raffle.entry_count += 1
        
        db.session.commit()
        
        return jsonify({'ok': True, 'new_points': viewer.points, 'entry_number': entry_number})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'message': str(e)}), 500


@kick_bp.route('/api/raffle/draw/<int:raffle_id>', methods=['POST'])
@login_required
def draw_raffle(raffle_id):
    """API: Ejecutar sorteo aleatorio (solo admin/streamer)"""
    from models import Raffle, RaffleEntry
    from app import db
    import random
    
    try:
        raffle = Raffle.query.get_or_404(raffle_id)
        
        # Verificar permisos
        if raffle.user_id and raffle.user_id != current_user.id:
            return jsonify({'ok': False, 'message': 'Sin permisos'}), 403
        
        # Verificar que está activo
        if not raffle.is_active:
            return jsonify({'ok': False, 'message': 'Sorteo no activo'}), 400
        
        # Obtener entradas
        entries = RaffleEntry.query.filter_by(raffle_id=raffle_id).all()
        if not entries:
            return jsonify({'ok': False, 'message': 'No hay participantes'}), 400
        
        # Elegir ganador aleatorio
        winner_entry = random.choice(entries)
        raffle.is_active = False
        raffle.winner_viewer_id = winner_entry.viewer_id
        
        db.session.commit()
        
        winner_username = winner_entry.viewer.username_kick
        
        return jsonify({
            'ok': True,
            'winner': winner_username,
            'entry_number': winner_entry.entry_number
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'message': str(e)}), 500


@kick_bp.route('/api/viewer/points/<username_kick>')
def get_viewer_points(username_kick):
    """API: Obtener puntos de un viewer"""
    from models import Viewer
    
    viewer = Viewer.query.filter_by(username_kick=username_kick).first()
    if not viewer:
        return jsonify({'ok': True, 'points': 0, 'watch_time': 0})
    
    return jsonify({
        'ok': True,
        'points': viewer.points,
        'watch_time': viewer.watch_time,
        'username_kick': viewer.username_kick
    })


@kick_bp.route('/api/raffles/active')
def get_active_raffles():
    """API: Obtener sorteos activos"""
    from models import Raffle
    
    raffles = Raffle.query.filter_by(is_active=True).all()
    
    return jsonify({
        'ok': True,
        'raffles': [{
            'id': r.id,
            'title': r.title,
            'description': r.description,
            'prize': r.prize,
            'entry_cost': r.entry_cost,
            'entry_count': r.entry_count,
            'max_entries': r.max_entries
        } for r in raffles]
    })


@kick_bp.route('/api/verify-username/<username>')
def verify_kick_username(username):
    """API: Verificar si un username existe en Kick"""
    from helpers.kick_api import get_channel_info
    
    try:
        # Intentar obtener info del canal
        channel_info = get_channel_info(username)
        
        # Verificar si hubo error (usuario no existe o API falló)
        if channel_info.get('error'):
            return jsonify({
                'ok': True,
                'exists': False,
                'message': 'Usuario no encontrado en Kick'
            })
        
        # Usuario existe
        return jsonify({
            'ok': True,
            'exists': True,
            'username': channel_info.get('username'),
            'display_name': channel_info.get('display_name', username)
        })
            
    except Exception as e:
        # Si hay excepción inesperada
        return jsonify({
            'ok': True,
            'exists': False,
            'message': 'Error al verificar username'
        })


@kick_bp.route('/api/points/config')
def get_points_config():
    """API: Obtener configuración actual de puntos - 3 sistemas principales"""
    from models import PointsConfig
    from app import db
    
    # Uso público sin company - usa None
    config = PointsConfig.get_or_create_default(company_id=None)
    db.session.commit()  # Commit si se creó
    
    return jsonify({
        'ok': True,
        'config': {
            'points_per_minute_watching': config.points_per_minute_watching,
            'daily_visit_points': config.daily_visit_points,
            'cooldown_seconds': config.cooldown_seconds,
            'max_points_per_day': config.max_points_per_day,
            'enabled': config.enabled
        }
    })


@kick_bp.route('/admin/points-config', methods=['GET', 'POST'])
@login_required
def points_config():
    """Configurar sistema de puntos de Kick (solo admin)"""
    from flask_login import current_user
    from forms import PointsConfigForm
    from models import PointsConfig
    from app import db
    
    # Solo admin puede acceder
    if not current_user.is_admin_global() and not current_user.is_admin_empresa():
        flash('No tienes permisos para acceder a esta página.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Obtener o crear configuración para la empresa del usuario
    config = PointsConfig.get_or_create_default(company_id=current_user.company_id)
    db.session.commit()  # Commit si se creó
    
    form = PointsConfigForm(obj=config)
    
    if form.validate_on_submit():
        # Actualizar configuración - 2 sistemas automáticos
        config.points_per_minute_watching = form.points_per_minute_watching.data
        config.daily_visit_points = form.daily_visit_points.data
        config.cooldown_seconds = form.cooldown_seconds.data
        config.max_points_per_day = form.max_points_per_day.data if form.max_points_per_day.data else None
        config.enabled = form.enabled.data
        
        db.session.commit()
        
        flash('Configuración de puntos actualizada exitosamente.', 'success')
        return redirect(url_for('kick.points_config'))
    
    return render_template('kick/points_config.html', form=form, config=config)


@kick_bp.route('/admin/redeem-codes', methods=['GET', 'POST'])
@login_required
def admin_redeem_codes():
    """Gestionar códigos canjeables (listar y crear nuevos)"""
    from flask_login import current_user
    from forms import RedeemCodeForm
    from models import RedeemCode
    from app import db
    
    # Solo admin puede acceder
    if not current_user.is_admin_global() and not current_user.is_admin_empresa():
        flash('No tienes permisos para acceder a esta página.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    form = RedeemCodeForm()
    
    if form.validate_on_submit():
        # Verificar que el código no exista
        existing_code = RedeemCode.query.filter_by(code=form.code.data.upper()).first()
        if existing_code:
            flash(f'El código "{form.code.data}" ya existe.', 'danger')
        else:
            # Crear nuevo código
            new_code = RedeemCode(
                code=form.code.data.upper(),
                description=form.description.data,
                points=form.points.data,
                max_uses=form.max_uses.data,
                expires_at=form.expires_at.data,
                is_active=form.is_active.data,
                user_id=current_user.id
            )
            db.session.add(new_code)
            db.session.commit()
            
            flash(f'Código "{new_code.code}" creado exitosamente.', 'success')
            return redirect(url_for('kick.admin_redeem_codes'))
    
    # Global admins ven todos los códigos, otros solo los suyos
    if current_user.is_admin_global():
        codes = RedeemCode.query.order_by(RedeemCode.created_at.desc()).all()
    else:
        codes = RedeemCode.query.filter_by(user_id=current_user.id).order_by(RedeemCode.created_at.desc()).all()
    
    return render_template('kick/admin_redeem_codes.html', form=form, codes=codes)


@kick_bp.route('/admin/redeem-codes/edit/<int:code_id>', methods=['GET', 'POST'])
@login_required
def edit_redeem_code(code_id):
    """Editar un código canjeable existente"""
    from flask_login import current_user
    from forms import RedeemCodeForm
    from models import RedeemCode
    from app import db
    
    # Verificar permisos de admin
    if not current_user.is_admin_global() and not current_user.is_admin_empresa():
        flash('No tienes permisos para acceder a esta página.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    code = RedeemCode.query.get_or_404(code_id)
    
    # Global admins pueden editar cualquier código, otros solo los suyos
    if not current_user.is_admin_global() and code.user_id != current_user.id:
        flash('No tienes permiso para editar este código.', 'danger')
        return redirect(url_for('kick.admin_redeem_codes'))
    
    form = RedeemCodeForm(obj=code)
    
    if form.validate_on_submit():
        # Verificar que el código no exista (excepto el actual)
        existing_code = RedeemCode.query.filter(
            RedeemCode.code == form.code.data.upper(),
            RedeemCode.id != code_id
        ).first()
        
        if existing_code:
            flash(f'El código "{form.code.data}" ya existe.', 'danger')
        else:
            code.code = form.code.data.upper()
            code.description = form.description.data
            code.points = form.points.data
            code.max_uses = form.max_uses.data
            code.expires_at = form.expires_at.data
            code.is_active = form.is_active.data
            
            db.session.commit()
            
            flash(f'Código "{code.code}" actualizado exitosamente.', 'success')
            return redirect(url_for('kick.admin_redeem_codes'))
    
    return render_template('kick/edit_redeem_code.html', form=form, code=code)


@kick_bp.route('/admin/redeem-codes/toggle/<int:code_id>', methods=['POST'])
@login_required
def toggle_redeem_code(code_id):
    """Activar/desactivar un código"""
    from flask_login import current_user
    from models import RedeemCode
    from app import db
    
    # Verificar permisos de admin
    if not current_user.is_admin_global() and not current_user.is_admin_empresa():
        flash('No tienes permisos para realizar esta acción.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    code = RedeemCode.query.get_or_404(code_id)
    
    # Global admins pueden modificar cualquier código, otros solo los suyos
    if not current_user.is_admin_global() and code.user_id != current_user.id:
        flash('No tienes permiso para modificar este código.', 'danger')
        return redirect(url_for('kick.admin_redeem_codes'))
    
    code.is_active = not code.is_active
    db.session.commit()
    
    status = 'activado' if code.is_active else 'desactivado'
    flash(f'Código "{code.code}" {status} exitosamente.', 'success')
    
    return redirect(url_for('kick.admin_redeem_codes'))


@kick_bp.route('/admin/redeem-codes/view/<int:code_id>')
@login_required
def view_redeem_code(code_id):
    """Ver detalles y estadísticas de un código"""
    from flask_login import current_user
    from models import RedeemCode
    
    # Verificar permisos de admin
    if not current_user.is_admin_global() and not current_user.is_admin_empresa():
        flash('No tienes permisos para acceder a esta página.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    code = RedeemCode.query.get_or_404(code_id)
    
    # Global admins pueden ver cualquier código, otros solo los suyos
    if not current_user.is_admin_global() and code.user_id != current_user.id:
        flash('No tienes permiso para ver este código.', 'danger')
        return redirect(url_for('kick.admin_redeem_codes'))
    
    return render_template('kick/view_redeem_code.html', code=code)


@kick_bp.route('/admin/redeem-codes/delete/<int:code_id>', methods=['POST'])
@login_required
def delete_redeem_code(code_id):
    """Eliminar un código canjeable"""
    from flask_login import current_user
    from models import RedeemCode
    from app import db
    
    # Verificar permisos de admin
    if not current_user.is_admin_global() and not current_user.is_admin_empresa():
        flash('No tienes permisos para realizar esta acción.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    code = RedeemCode.query.get_or_404(code_id)
    
    # Global admins pueden eliminar cualquier código, otros solo los suyos
    if not current_user.is_admin_global() and code.user_id != current_user.id:
        flash('No tienes permiso para eliminar este código.', 'danger')
        return redirect(url_for('kick.admin_redeem_codes'))
    
    code_name = code.code
    db.session.delete(code)
    db.session.commit()
    
    flash(f'Código "{code_name}" eliminado exitosamente.', 'success')
    return redirect(url_for('kick.admin_redeem_codes'))


# ===== API ENDPOINTS PARA SISTEMA DE PUNTOS EXTRA =====

@kick_bp.route('/api/daily-visit', methods=['POST'])
@csrf.exempt
def daily_visit():
    """API: Registrar visita diaria y otorgar puntos de bienvenida"""
    from models import Viewer, DailyVisit, PointsConfig
    from app import db
    from datetime import datetime, date
    
    try:
        data = request.json
        username_kick = data.get('username_kick')
        
        if not username_kick:
            return jsonify({'ok': False, 'message': 'Username es requerido'}), 400
        
        # Obtener configuración de puntos
        config = PointsConfig.query.filter_by(company_id=None).first()
        if not config or not config.enabled:
            return jsonify({'ok': False, 'message': 'Sistema de puntos desactivado'}), 403
        
        # Buscar o crear viewer
        viewer = Viewer.query.filter_by(username_kick=username_kick).first()
        if not viewer:
            # Nuevo viewer - crear con puntos de bienvenida (desde config)
            daily_points = config.daily_visit_points
            viewer = Viewer(
                username_kick=username_kick,
                points=daily_points,
                watch_time=0,
                messages_sent=0
            )
            db.session.add(viewer)
            db.session.flush()
            
            # Registrar visita
            visit = DailyVisit(
                viewer_id=viewer.id,
                visit_date=date.today(),
                points_awarded=daily_points
            )
            db.session.add(visit)
            db.session.commit()
            
            return jsonify({
                'ok': True,
                'first_visit': True,
                'points_awarded': daily_points,
                'total_points': viewer.points,
                'message': f'¡Bienvenido! +{daily_points} puntos por tu primera visita'
            })
        
        # Verificar si ya visitó hoy
        today = date.today()
        visit_today = DailyVisit.query.filter_by(
            viewer_id=viewer.id,
            visit_date=today
        ).first()
        
        if visit_today:
            # Ya visitó hoy - no dar puntos
            return jsonify({
                'ok': True,
                'already_visited': True,
                'total_points': viewer.points,
                'message': 'Ya recibiste tus puntos de visita diaria'
            })
        
        # Primera visita del día - dar puntos (desde config)
        daily_points = config.daily_visit_points
        viewer.points += daily_points
        visit = DailyVisit(
            viewer_id=viewer.id,
            visit_date=today,
            points_awarded=daily_points
        )
        db.session.add(visit)
        db.session.commit()
        
        return jsonify({
            'ok': True,
            'first_visit': False,
            'points_awarded': daily_points,
            'total_points': viewer.points,
            'message': f'¡Bienvenido de nuevo! +{daily_points} puntos por visitar hoy'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'message': str(e)}), 500


@kick_bp.route('/api/redeem-code', methods=['POST'])
@csrf.exempt
def redeem_code():
    """API: Canjear código para obtener puntos"""
    from models import Viewer, RedeemCode, CodeRedemption, PointsConfig
    from app import db
    from datetime import datetime
    
    try:
        data = request.json
        username_kick = data.get('username_kick')
        code_text = data.get('code')
        
        if not username_kick or not code_text:
            return jsonify({'ok': False, 'message': 'Username y código son requeridos'}), 400
        
        # Verificar que el sistema de puntos esté habilitado
        config = PointsConfig.query.filter_by(company_id=None).first()
        if not config or not config.enabled:
            return jsonify({'ok': False, 'message': 'Sistema de puntos desactivado'}), 403
        
        # Buscar viewer
        viewer = Viewer.query.filter_by(username_kick=username_kick).first()
        if not viewer:
            return jsonify({'ok': False, 'message': 'Usuario no encontrado. Ingresa tu username primero.'}), 404
        
        # Buscar código (case-insensitive)
        code = RedeemCode.query.filter(
            db.func.upper(RedeemCode.code) == code_text.upper()
        ).first()
        
        if not code:
            return jsonify({'ok': False, 'message': 'Código inválido'}), 404
        
        # Verificar si el código está disponible
        if not code.is_available:
            if not code.is_active:
                return jsonify({'ok': False, 'message': 'Código desactivado'}), 400
            elif code.current_uses >= code.max_uses:
                return jsonify({'ok': False, 'message': 'Código agotado'}), 400
            elif code.expires_at and datetime.utcnow() > code.expires_at:
                return jsonify({'ok': False, 'message': 'Código expirado'}), 400
        
        # Verificar si el viewer ya usó este código
        existing_redemption = CodeRedemption.query.filter_by(
            code_id=code.id,
            viewer_id=viewer.id
        ).first()
        
        if existing_redemption:
            return jsonify({'ok': False, 'message': 'Ya canjeaste este código anteriormente'}), 400
        
        # Canjear código - otorgar puntos
        viewer.points += code.points
        code.current_uses += 1
        
        redemption = CodeRedemption(
            code_id=code.id,
            viewer_id=viewer.id,
            points_awarded=code.points
        )
        db.session.add(redemption)
        db.session.commit()
        
        return jsonify({
            'ok': True,
            'points_awarded': code.points,
            'total_points': viewer.points,
            'code': code.code,
            'message': f'¡Código canjeado! +{code.points} puntos'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'message': str(e)}), 500
