from flask import render_template, redirect, url_for, flash, request
from datetime import datetime, timedelta
from . import public
from models import Company, Service, Appointment, User, PublicPage
from forms import PublicAppointmentForm
from app import db
import json
import requests
import csv
from io import StringIO

# Cache simple para wager race (5 minutos)
_wager_race_cache = {
    'data': None,
    'timestamp': None
}

STAKE_CSV_URL = "https://app.trevor.io/share/view/6d12c9ec-8941-43a8-ba73-15cafbe6bb30/1d/YANGLEELOL_Affiliate_Stake_com_Wager_Race_Statistics_Auto_Update_Current_Past_Month.csv?seed=32"
CACHE_DURATION = timedelta(minutes=5)

def get_wager_race_data():
    """Obtiene y parsea los datos del CSV de Stake Wager Race con cache"""
    global _wager_race_cache
    
    # Verificar cache
    now = datetime.now()
    if _wager_race_cache['data'] and _wager_race_cache['timestamp']:
        if now - _wager_race_cache['timestamp'] < CACHE_DURATION:
            return _wager_race_cache['data']
    
    try:
        # Fetch CSV
        response = requests.get(STAKE_CSV_URL, timeout=10)
        response.raise_for_status()
        
        # Parsear CSV
        csv_data = StringIO(response.text)
        reader = csv.DictReader(csv_data)
        
        # Separar períodos actual y anterior
        current_period = []
        previous_period = []
        
        for row in reader:
            try:
                entry = {
                    'username': row.get('user_name', '').strip(),
                    'wagered': float(row.get('wagered', 0)),
                    'rank': int(row.get('rank', 0)),
                    'start_date': row.get('start_date_utc', ''),
                    'end_date': row.get('end_date_utc', '')
                }
                
                # Determinar período (actual vs anterior)
                # El CSV tiene dos bloques: Top 100 actual, luego Top anterior
                if entry['start_date'].startswith('2025-10'):
                    current_period.append(entry)
                elif entry['start_date'].startswith('2025-09'):
                    previous_period.append(entry)
            except (ValueError, KeyError) as e:
                print(f"Error procesando fila del CSV: {e}")
                continue
        
        # Ordenar por rank
        current_period.sort(key=lambda x: x['rank'])
        previous_period.sort(key=lambda x: x['rank'])
        
        result = {
            'current': current_period,
            'previous': previous_period,
            'updated_at': now
        }
        
        # Actualizar cache
        _wager_race_cache['data'] = result
        _wager_race_cache['timestamp'] = now
        
        return result
        
    except Exception as e:
        print(f"Error obteniendo datos de Wager Race: {e}")
        # Retornar cache antiguo si existe, sino None
        return _wager_race_cache.get('data')

@public.route('/empresa/<company_code>')
def portfolio(company_code):
    """Página pública de presentación de empresa"""
    company = Company.query.filter_by(code=company_code, is_active=True).first_or_404()
    
    if not company.module_portfolio:
        return render_template('errors/module_disabled.html'), 404
    
    # URL de reserva si tiene módulo de citas activo
    booking_url = None
    if company.module_appointments:
        booking_url = url_for('public.booking', company_code=company.code)
    
    return render_template('public/portfolio.html', company=company, booking_url=booking_url, current_year=datetime.now().year)

@public.route('/empresa/<company_code>/reservar', methods=['GET', 'POST'])
def booking(company_code):
    """Página pública para reservar citas"""
    company = Company.query.filter_by(code=company_code, is_active=True).first_or_404()
    
    if not company.module_appointments:
        return render_template('errors/module_disabled.html'), 404
    
    form = PublicAppointmentForm()
    
    # Cargar servicios activos
    services = Service.query.filter_by(company_id=company.id, is_active=True).all()
    form.service_id.choices = [(s.id, f"{s.name} ({s.duration_minutes} min)") for s in services]
    
    if form.validate_on_submit():
        appointment = Appointment()
        appointment.client_name = form.client_name.data
        appointment.client_phone = form.client_phone.data
        appointment.client_email = form.client_email.data
        appointment.appointment_date = form.appointment_date.data
        appointment.service_id = form.service_id.data
        appointment.notes = form.notes.data
        appointment.is_public = True
        appointment.company_id = company.id
        appointment.status = 'pendiente'
        db.session.add(appointment)
        db.session.commit()
        
        flash('¡Reserva realizada exitosamente! Te contactaremos pronto para confirmar.', 'success')
        return redirect(url_for('public.booking_confirmation', company_code=company.code, appointment_id=appointment.id))
    
    return render_template('public/booking.html', company=company, form=form, services=services)

@public.route('/empresa/<company_code>/reserva/<int:appointment_id>/confirmacion')
def booking_confirmation(company_code, appointment_id):
    """Confirmación de reserva"""
    company = Company.query.filter_by(code=company_code, is_active=True).first_or_404()
    appointment = Appointment.query.filter_by(id=appointment_id, company_id=company.id).first_or_404()
    
    return render_template('public/booking_confirmation.html', 
                         company=company, appointment=appointment)

@public.route('/yanglee')
def yanglee_page():
    """Página pública personalizada de Yanglee - Redirige a perfil dinámico con JSON"""
    return perfil_dinamico('yangprroo@gmail.com')

@public.route('/perfil/<email>')
def perfil_dinamico(email):
    """Página pública dinámica basada en JSON para cualquier usuario"""
    import os
    from urllib.parse import unquote_plus
    from flask import session, request
    
    # Decodificar email si viene URL-encoded
    email = unquote_plus(email)
    
    # Leer archivo JSON
    json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'user_data.json')
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            usuarios = json.load(f)
    except FileNotFoundError:
        return render_template('errors/404.html', message="Archivo de usuarios no encontrado"), 404
    except json.JSONDecodeError:
        return render_template('errors/404.html', message="Error al leer datos de usuarios"), 500
    
    # Buscar usuario por email
    usuario_data = None
    for user in usuarios:
        if user.get('email', '').lower() == email.lower():
            usuario_data = user
            break
    
    # Si no se encuentra el usuario
    if not usuario_data:
        return render_template('errors/404.html', message=f"Usuario con email '{email}' no encontrado"), 404
    
    # Preparar datos para el template (similar a yanglee_page)
    # Crear objeto similar a PublicPage para compatibilidad con la plantilla
    page_data = {
        'title': usuario_data.get('nombre', 'Usuario'),
        'description': usuario_data.get('descripcion', ''),
        'profile_image_url': usuario_data.get('foto_perfil', ''),
        'primary_color': usuario_data.get('color_primario', '#ff6600'),
        'secondary_color': usuario_data.get('color_secundario', '#1a1a1a'),
        'background_type': 'gradient',
        'background_value': 'linear-gradient(135deg, #1a1a1a 0%, #2c2c2c 100%)'
    }
    
    # Redes sociales
    social_links = usuario_data.get('redes', {})
    
    # Secciones (por defecto todas activas)
    sections = {
        'bio': True,
        'clips': True,
        'gallery': True,
        'contact': True
    }
    
    # Crear objeto usuario con email y nombre
    user_obj = type('obj', (object,), {
        'email': usuario_data.get('email', ''),
        'username': usuario_data.get('nombre', '')
    })()
    
    # Obtener clips del usuario desde la base de datos
    clips = []
    featured_clip = None
    try:
        from models import Clip
        db_user = User.query.filter_by(email=email).first()
        if db_user:
            clips = Clip.query.filter_by(user_id=db_user.id).order_by(Clip.order_position, Clip.created_at).all()
            # Obtener clip destacado
            featured_clip = Clip.query.filter_by(user_id=db_user.id, is_featured=True).first()
    except Exception as e:
        print(f"Error al cargar clips: {e}")
    
    # ===== INTEGRACIÓN CON KICK API =====
    kick_data = None
    kick_stream_status = None
    kick_channel_info = None
    
    kick_username = usuario_data.get('kick_username')
    if kick_username:
        try:
            from helpers.kick_api import get_stream_status, get_channel_info
            kick_stream_status = get_stream_status(kick_username)
            kick_channel_info = get_channel_info(kick_username)
            
            kick_data = {
                'username': kick_username,
                'stream': kick_stream_status,
                'channel': kick_channel_info
            }
        except Exception as e:
            print(f"Error al cargar datos de Kick: {e}")
    
    # ===== SISTEMA DE SORTEOS =====
    sorteos_activos = []
    sorteos_habilitados = usuario_data.get('sorteos_habilitados', False)
    
    if sorteos_habilitados and kick_username:
        try:
            from models import Raffle
            # Obtener usuario de Workly por email para los sorteos
            db_user = User.query.filter_by(email=email).first()
            if db_user:
                # Sorteos activos del streamer
                sorteos_activos = Raffle.query.filter_by(
                    user_id=db_user.id,
                    status='active'
                ).filter(
                    (Raffle.end_date == None) | (Raffle.end_date > datetime.now())
                ).all()
        except Exception as e:
            print(f"Error al cargar sorteos: {e}")
    
    # Verificar si el usuario está autenticado con Kick
    kick_user_authenticated = 'kick_user_id' in session
    kick_username_authenticated = session.get('kick_username')
    
    # ===== WAGER RACE DE STAKE =====
    wager_race_data = None
    if usuario_data.get('stake_wager_race_enabled', True):
        wager_race_data = get_wager_race_data()
    
    # Pasar todos los datos del JSON al template
    return render_template('public/public_page.html', 
                         user=user_obj,
                         page=type('obj', (object,), page_data)(),
                         social_links=social_links,
                         sections=sections,
                         usuario_json=usuario_data,
                         clips=clips,
                         featured_clip=featured_clip,
                         kick_data=kick_data,
                         sorteos_activos=sorteos_activos,
                         sorteos_habilitados=sorteos_habilitados,
                         kick_user_authenticated=kick_user_authenticated,
                         kick_username_authenticated=kick_username_authenticated,
                         wager_race=wager_race_data,
                         request=request)


# ===== PANEL ADMIN DE CLIPS =====

@public.route('/admin/clips')
def admin_clips():
    """Panel de administración de clips de video"""
    from flask_login import login_required, current_user
    from models import Clip
    
    # Aplicar login_required manualmente
    if not current_user.is_authenticated:
        flash('Debes iniciar sesión para acceder a esta página.', 'danger')
        return redirect(url_for('login'))
    
    # Obtener todos los clips del usuario actual
    clips = Clip.query.filter_by(user_id=current_user.id).order_by(Clip.order_position, Clip.created_at.desc()).all()
    
    return render_template('public/admin_clips.html', clips=clips)


@public.route('/admin/clips/create', methods=['GET', 'POST'])
def create_clip():
    """Crear un nuevo clip de video"""
    from flask_login import login_required, current_user
    from forms import ClipForm
    from models import Clip
    
    # Aplicar login_required manualmente
    if not current_user.is_authenticated:
        flash('Debes iniciar sesión para acceder a esta página.', 'danger')
        return redirect(url_for('login'))
    
    form = ClipForm()
    
    if form.validate_on_submit():
        # Verificar límite de 3 clips por usuario (opcional)
        clip_count = Clip.query.filter_by(user_id=current_user.id).count()
        
        clip = Clip(
            user_id=current_user.id,
            video_url=form.video_url.data,
            title=form.title.data,
            description=form.description.data,
            thumbnail_url=form.thumbnail_url.data,
            featured_thumbnail_url=form.featured_thumbnail_url.data,
            is_featured=form.is_featured.data,
            order_position=form.order_position.data if form.order_position.data else 0
        )
        
        db.session.add(clip)
        db.session.commit()
        
        flash(f'Clip "{clip.title or "sin título"}" creado exitosamente.', 'success')
        return redirect(url_for('public.admin_clips'))
    
    return render_template('public/create_clip.html', form=form)


@public.route('/admin/clips/<int:clip_id>/edit', methods=['GET', 'POST'])
def edit_clip(clip_id):
    """Editar un clip existente"""
    from flask_login import login_required, current_user
    from forms import ClipForm
    from models import Clip
    
    # Aplicar login_required manualmente
    if not current_user.is_authenticated:
        flash('Debes iniciar sesión para acceder a esta página.', 'danger')
        return redirect(url_for('login'))
    
    clip = Clip.query.get_or_404(clip_id)
    
    # Verificar que el clip pertenece al usuario
    if clip.user_id != current_user.id:
        flash('No tienes permiso para editar este clip.', 'danger')
        return redirect(url_for('public.admin_clips'))
    
    form = ClipForm(obj=clip)
    
    if form.validate_on_submit():
        clip.video_url = form.video_url.data
        clip.title = form.title.data
        clip.description = form.description.data
        clip.thumbnail_url = form.thumbnail_url.data
        clip.featured_thumbnail_url = form.featured_thumbnail_url.data
        clip.is_featured = form.is_featured.data
        clip.order_position = form.order_position.data if form.order_position.data else 0
        
        db.session.commit()
        
        flash(f'Clip "{clip.title or "sin título"}" actualizado exitosamente.', 'success')
        return redirect(url_for('public.admin_clips'))
    
    return render_template('public/edit_clip.html', form=form, clip=clip)


@public.route('/admin/clips/<int:clip_id>/delete', methods=['POST'])
def delete_clip(clip_id):
    """Eliminar un clip permanentemente"""
    from flask_login import login_required, current_user
    from models import Clip
    
    # Aplicar login_required manualmente
    if not current_user.is_authenticated:
        flash('Debes iniciar sesión para acceder a esta página.', 'danger')
        return redirect(url_for('login'))
    
    clip = Clip.query.get_or_404(clip_id)
    
    # Verificar que el clip pertenece al usuario
    if clip.user_id != current_user.id:
        flash('No tienes permiso para eliminar este clip.', 'danger')
        return redirect(url_for('public.admin_clips'))
    
    # Guardar título para el mensaje
    titulo = clip.title or "sin título"
    
    # Eliminar clip
    db.session.delete(clip)
    db.session.commit()
    
    flash(f'Clip "{titulo}" eliminado permanentemente.', 'success')
    return redirect(url_for('public.admin_clips'))