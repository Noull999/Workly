from flask import render_template, redirect, url_for, flash, request, jsonify, current_app, send_file, Response
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from . import tipeos_bp
from .forms import TipeoUnificadoForm
from app import db
from models import TipeoAvailable, TipeoRequest, UserNotification, Viewer, User, RankPeriod, RankPeriodUser, StakeKickLink
from datetime import datetime
from blueprints.public.routes import get_wager_race_data
import os
import uuid
import logging
import re

try:
    from replit.object_storage import Client as ObjectStorageClient
    object_storage = ObjectStorageClient()
    OBJECT_STORAGE_AVAILABLE = True
except Exception as e:
    logging.warning(f"Object Storage not available: {e}")
    object_storage = None
    OBJECT_STORAGE_AVAILABLE = False

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
UPLOAD_FOLDER = 'static/uploads/tipeos'
STREAMER_EMAIL = 'yangprroo@gmail.com'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_streamer_or_admin():
    """Verifica si el usuario actual es el streamer o admin global"""
    return current_user.is_admin_global() or current_user.email == STREAMER_EMAIL

def ensure_upload_folder():
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def save_image_to_storage(image_data, filename):
    """Guarda imagen en Object Storage (persistente) y local (fallback)"""
    object_key = f"tipeos/{filename}"
    
    if OBJECT_STORAGE_AVAILABLE and object_storage:
        try:
            object_storage.upload_from_bytes(object_key, image_data)
            logging.info(f"Image saved to Object Storage: {object_key}")
        except Exception as e:
            logging.error(f"Failed to upload to Object Storage: {e}")
    
    ensure_upload_folder()
    local_path = os.path.join(UPLOAD_FOLDER, filename)
    try:
        with open(local_path, 'wb') as f:
            f.write(image_data)
    except Exception as e:
        logging.error(f"Failed to save locally: {e}")
    
    return f'/tipeos/imagen/{filename}'

def get_image_from_storage(filename):
    """Obtiene imagen de Object Storage o local"""
    object_key = f"tipeos/{filename}"
    
    if OBJECT_STORAGE_AVAILABLE and object_storage:
        try:
            data = object_storage.download_as_bytes(object_key)
            if data:
                return data
        except Exception as e:
            logging.debug(f"Not in Object Storage, trying local: {e}")
    
    local_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(local_path):
        with open(local_path, 'rb') as f:
            return f.read()
    
    return None


# ===== FORMULARIO UNIFICADO DE TIPEOS =====

@tipeos_bp.route('/', methods=['GET', 'POST'])
def formulario_tipeo():
    """Formulario unificado para solicitar tipeos"""
    form = TipeoUnificadoForm()
    mis_solicitudes = []
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'multipart/form-data'
    
    if form.validate_on_submit():
        stake_username = form.stake_username.data.strip()
        trx_address = form.trx_address.data.strip()
        
        # Validar formato TRX
        if not re.match(r'^T[a-zA-Z0-9]{33}$', trx_address):
            if is_ajax:
                return jsonify({'success': False, 'error': 'El formato de la dirección TRX es inválido'}), 400
            flash('El formato de la dirección TRX es inválido', 'error')
            return render_template('tipeos/formulario.html', form=form, mis_solicitudes=mis_solicitudes)
        
        # Verificar si ya tiene una solicitud activa
        solicitud_activa = TipeoRequest.query.filter(
            TipeoRequest.stake_username == stake_username,
            TipeoRequest.status == 'submitted'
        ).first()
        
        if solicitud_activa:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Ya tienes una solicitud pendiente. Espera a que sea procesada.'}), 400
            flash('Ya tienes una solicitud pendiente. Espera a que sea procesada.', 'warning')
            return render_template('tipeos/formulario.html', form=form, mis_solicitudes=mis_solicitudes)
        
        try:
            # Guardar imagen 1 (usuario Stake)
            image1 = form.image_stake_user.data
            filename1 = f"{uuid.uuid4().hex}_{secure_filename(image1.filename)}"
            image1_data = image1.read()
            image1_url = save_image_to_storage(image1_data, filename1)
            
            # Guardar imagen 2 (código patrocinador)
            image2 = form.image_sponsor_code.data
            filename2 = f"{uuid.uuid4().hex}_{secure_filename(image2.filename)}"
            image2_data = image2.read()
            image2_url = save_image_to_storage(image2_data, filename2)
            
            # Buscar viewer existente por stake_username
            viewer = Viewer.query.filter(
                db.func.lower(Viewer.stake_username) == stake_username.lower()
            ).first()
            
            # Crear solicitud
            nueva_solicitud = TipeoRequest(
                stake_username=stake_username,
                trx_address=trx_address,
                trx_code=form.trx_code.data.strip(),
                tipeo_type=form.tipeo_type.data,
                image_stake_user=image1_url,
                image_sponsor_code=image2_url,
                comments=form.comments.data.strip() if form.comments.data else None,
                status='submitted',
                viewer_id=viewer.id if viewer else None,
                # Campos legacy para compatibilidad
                nick_stake=stake_username,
                red_crypto='TRX'
            )
            
            db.session.add(nueva_solicitud)
            db.session.commit()
            
            if is_ajax:
                return jsonify({'success': True, 'message': '¡Solicitud enviada correctamente! Te notificaremos cuando sea procesada.'})
            
            flash('¡Solicitud enviada correctamente! Te notificaremos cuando sea procesada.', 'success')
            return redirect(url_for('tipeos.formulario_tipeo'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error al crear solicitud de tipeo: {e}")
            if is_ajax:
                return jsonify({'success': False, 'error': 'Error al procesar la solicitud. Intenta nuevamente.'}), 500
            flash('Error al procesar la solicitud. Intenta nuevamente.', 'error')
    
    # Manejar errores de validación para AJAX
    if request.method == 'POST' and is_ajax and not form.validate():
        errors = []
        for field, errs in form.errors.items():
            for err in errs:
                errors.append(f"{field}: {err}")
        return jsonify({'success': False, 'error': '; '.join(errors) if errors else 'Error de validación'}), 400
    
    return render_template('tipeos/formulario.html', form=form, mis_solicitudes=mis_solicitudes)


@tipeos_bp.route('/serve-tutorial-video')
def serve_tutorial_video():
    """Sirve el video tutorial desde Object Storage o local"""
    video_paths = [
        'videos/tipeo-tutorial.mp4',
        'tipeo-tutorial.mp4',
        'videos/tipeo-tutorial.mkv',
        'tipeo-tutorial.mkv'
    ]
    
    # Intentar desde Object Storage
    if OBJECT_STORAGE_AVAILABLE and object_storage:
        for path in video_paths:
            try:
                data = object_storage.download_as_bytes(path)
                if data:
                    content_type = 'video/mp4' if path.endswith('.mp4') else 'video/x-matroska'
                    return Response(data, mimetype=content_type)
            except Exception:
                continue
    
    # Fallback a archivo local
    local_paths = [
        'static/videos/tipeo-tutorial.mp4',
        'static/videos/tipeo-tutorial.mkv'
    ]
    for path in local_paths:
        if os.path.exists(path):
            return send_file(path)
    
    return 'Video no disponible', 404


@tipeos_bp.route('/admin/usuarios')
@login_required
def admin_usuarios():
    """Vista de tabla informativa de usuarios para admin/streamer"""
    if not is_streamer_or_admin():
        flash('Acceso denegado', 'error')
        return redirect(url_for('dashboard'))
    
    wager_race_data = get_wager_race_data()
    
    usuarios_wager = []
    periodo_info = None
    
    if wager_race_data and wager_race_data.get('current'):
        current_players = wager_race_data['current']
        if current_players:
            first_player = current_players[0]
            periodo_info = {
                'start_date': first_player.get('start_date', ''),
                'end_date': first_player.get('end_date', ''),
                'total_players': len(current_players)
            }
        
        for player in current_players:
            stake_username = player.get('username', '')
            wagered = player.get('wagered', 0)
            rank = player.get('rank', 0)
            
            link = StakeKickLink.query.filter(
                db.func.lower(StakeKickLink.stake_username) == stake_username.lower()
            ).first()
            viewer = link.viewer if link and link.viewer_id else None
            auto_vinculado = False
            
            if not viewer:
                viewer_auto = Viewer.query.filter(
                    db.func.lower(Viewer.stake_username) == stake_username.lower(),
                    Viewer.stake_verified == True
                ).first()
                if viewer_auto:
                    viewer = viewer_auto
                    auto_vinculado = True
            
            tipeo_disponible = False
            tipeo_pendiente = False
            tipeos_otorgados = 0
            if viewer:
                tipeo_disponible = TipeoAvailable.query.filter_by(
                    viewer_id=viewer.id, status='available'
                ).first() is not None
                tipeo_pendiente = TipeoRequest.query.filter_by(
                    viewer_id=viewer.id, status='submitted'
                ).first() is not None
                tipeos_otorgados = TipeoRequest.query.filter_by(
                    viewer_id=viewer.id, status='approved'
                ).count()
            
            vinculado = (link is not None and link.viewer_id is not None) or auto_vinculado
            
            usuarios_wager.append({
                'stake_username': stake_username,
                'wagered': wagered,
                'rank': rank,
                'link': link,
                'viewer': viewer,
                'vinculado': vinculado,
                'auto_vinculado': auto_vinculado,
                'tipeo_disponible': tipeo_disponible,
                'tipeo_pendiente': tipeo_pendiente,
                'tipeos_otorgados': tipeos_otorgados
            })
    
    viewers_kick = Viewer.query.order_by(Viewer.username_kick).all()
    
    total_vinculados = sum(1 for u in usuarios_wager if u['vinculado'])
    total_sin_vincular = sum(1 for u in usuarios_wager if not u['vinculado'])
    total_tipeos = sum(1 for u in usuarios_wager if u['tipeos_otorgados'] > 0)
    
    return render_template('tipeos/admin_usuarios.html', 
                           usuarios_wager=usuarios_wager, 
                           periodo=periodo_info,
                           viewers_kick=viewers_kick,
                           total_vinculados=total_vinculados,
                           total_sin_vincular=total_sin_vincular,
                           total_tipeos=total_tipeos)


@tipeos_bp.route('/admin/dar-tipeo/<int:viewer_id>', methods=['POST'])
@login_required
def dar_tipeo(viewer_id):
    """Admin otorga un tipeo disponible a un usuario"""
    if not is_streamer_or_admin():
        return jsonify({'success': False, 'error': 'Acceso denegado'}), 403
    
    viewer = Viewer.query.get_or_404(viewer_id)
    
    tipeo_existente = TipeoAvailable.query.filter_by(
        viewer_id=viewer_id,
        status='available'
    ).first()
    
    if tipeo_existente:
        return jsonify({'success': False, 'error': 'El usuario ya tiene un tipeo disponible'}), 400
    
    nuevo_tipeo = TipeoAvailable(
        viewer_id=viewer_id,
        granted_by_id=current_user.id,
        status='available'
    )
    db.session.add(nuevo_tipeo)
    
    notificacion = UserNotification(
        viewer_id=viewer_id,
        title='🎉 ¡Tienes un tipeo disponible!',
        message='YANGLEE te ha otorgado un tipeo. Ve a la sección de tipeos para completar el proceso.',
        notification_type='tipeo',
        action_url='#tipeo-section'
    )
    db.session.add(notificacion)
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Tipeo otorgado a {viewer.username_kick}'
    })


@tipeos_bp.route('/admin/dar-tipeo-especial', methods=['POST'])
@login_required
def dar_tipeo_especial():
    """Admin otorga un tipeo especial a un usuario de Kick (no en wager race)"""
    if not is_streamer_or_admin():
        return jsonify({'success': False, 'error': 'Acceso denegado'}), 403
    
    viewer_id = request.form.get('viewer_id')
    motivo = request.form.get('motivo', 'otro')
    
    if not viewer_id:
        return jsonify({'success': False, 'error': 'Selecciona un usuario'}), 400
    
    viewer = Viewer.query.get(int(viewer_id))
    if not viewer:
        return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
    
    tipeo_existente = TipeoAvailable.query.filter_by(
        viewer_id=viewer.id,
        status='available'
    ).first()
    
    if tipeo_existente:
        return jsonify({'success': False, 'error': f'{viewer.username_kick} ya tiene un tipeo disponible'}), 400
    
    motivos_texto = {
        'bonus_hunt': '🔥 Bonus Hunt',
        'tipeo_azar': '🎲 Tipeo al Azar',
        'sorteo_semanal': '🎁 Sorteo Semanal',
        'otro': '✨ Tipeo Especial'
    }
    motivo_texto = motivos_texto.get(motivo, '✨ Tipeo Especial')
    
    nuevo_tipeo = TipeoAvailable(
        viewer_id=viewer.id,
        granted_by_id=current_user.id,
        status='available'
    )
    db.session.add(nuevo_tipeo)
    
    notificacion = UserNotification(
        viewer_id=viewer.id,
        title=f'🎉 ¡Tienes un tipeo! - {motivo_texto}',
        message=f'YANGLEE te ha otorgado un tipeo por {motivo_texto}. Ve a la sección "Mi Tipeo" para reclamarlo.',
        notification_type='tipeo',
        action_url='#tipeo-section'
    )
    db.session.add(notificacion)
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Tipeo especial otorgado a {viewer.username_kick} ({motivo_texto})'
    })


@tipeos_bp.route('/admin/vincular', methods=['POST'])
@login_required
def vincular_stake_kick():
    """Vincula un usuario de Stake con una cuenta de Kick"""
    if not is_streamer_or_admin():
        return jsonify({'success': False, 'error': 'Acceso denegado'}), 403
    
    stake_username = request.form.get('stake_username')
    viewer_id = request.form.get('viewer_id')
    
    if not stake_username or not viewer_id:
        return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
    
    viewer = Viewer.query.get(int(viewer_id))
    if not viewer:
        return jsonify({'success': False, 'error': 'Usuario de Kick no encontrado'}), 404
    
    link = StakeKickLink.query.filter_by(stake_username=stake_username).first()
    if link:
        link.viewer_id = viewer.id
        link.is_verified = True
        link.verified_by_id = current_user.id
        link.verified_at = datetime.utcnow()
    else:
        link = StakeKickLink(
            stake_username=stake_username,
            viewer_id=viewer.id,
            is_verified=True,
            verified_by_id=current_user.id,
            verified_at=datetime.utcnow()
        )
        db.session.add(link)
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'{stake_username} vinculado con {viewer.username_kick}'
    })


@tipeos_bp.route('/admin/desvincular/<stake_username>', methods=['POST'])
@login_required
def desvincular_stake_kick(stake_username):
    """Desvincula un usuario de Stake de su cuenta de Kick"""
    if not is_streamer_or_admin():
        return jsonify({'success': False, 'error': 'Acceso denegado'}), 403
    
    desvinculado = False
    
    link = StakeKickLink.query.filter_by(stake_username=stake_username).first()
    if link:
        link.viewer_id = None
        link.is_verified = False
        desvinculado = True
    
    viewer_auto = Viewer.query.filter(
        db.func.lower(Viewer.stake_username) == stake_username.lower()
    ).first()
    if viewer_auto:
        viewer_auto.stake_username = None
        viewer_auto.stake_verified = False
        desvinculado = True
    
    if desvinculado:
        db.session.commit()
        return jsonify({'success': True, 'message': 'Desvinculado correctamente'})
    
    return jsonify({'success': False, 'error': 'Vinculación no encontrada'}), 404


@tipeos_bp.route('/admin/solicitudes')
@login_required
def admin_solicitudes():
    """Vista de solicitudes de tipeo pendientes"""
    if not is_streamer_or_admin():
        flash('Acceso denegado', 'error')
        return redirect(url_for('dashboard'))
    
    solicitudes = TipeoRequest.query.order_by(TipeoRequest.created_at.desc()).all()
    
    return render_template('tipeos/admin_solicitudes.html', solicitudes=solicitudes)


@tipeos_bp.route('/admin/aprobar/<int:request_id>', methods=['POST'])
@login_required
def aprobar_tipeo(request_id):
    """Admin aprueba una solicitud de tipeo y vincula cuentas automáticamente"""
    if not is_streamer_or_admin():
        return jsonify({'success': False, 'error': 'Acceso denegado'}), 403
    
    solicitud = TipeoRequest.query.get_or_404(request_id)
    
    solicitud.status = 'completed'
    solicitud.reviewed_by_id = current_user.id
    solicitud.reviewed_at = datetime.utcnow()
    
    tipeo_available = solicitud.tipeo_available
    if tipeo_available:
        tipeo_available.status = 'completed'
    
    # VINCULAR AUTOMÁTICAMENTE las cuentas al aprobar
    viewer = solicitud.viewer
    stake_name = solicitud.stake_username or solicitud.nick_stake
    if viewer and stake_name:
        viewer.stake_username = stake_name
        viewer.stake_verified = True
    
    # Solo crear notificación si hay viewer asociado
    if solicitud.viewer_id:
        notificacion = UserNotification(
            viewer_id=solicitud.viewer_id,
            title='✅ ¡Tu tipeo fue aprobado!',
            message=f'Tu solicitud de tipeo ha sido aprobada. Tu cuenta de Stake ({stake_name}) ha sido procesada.',
            notification_type='success'
        )
        db.session.add(notificacion)
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Tipeo aprobado y cuentas vinculadas'})


@tipeos_bp.route('/admin/rechazar/<int:request_id>', methods=['POST'])
@login_required
def rechazar_tipeo(request_id):
    """Admin rechaza una solicitud de tipeo"""
    if not is_streamer_or_admin():
        return jsonify({'success': False, 'error': 'Acceso denegado'}), 403
    
    solicitud = TipeoRequest.query.get_or_404(request_id)
    motivo = request.form.get('motivo', 'Sin motivo especificado')
    rechazo_definitivo = request.form.get('rechazo_definitivo', '0') == '1'
    
    solicitud.status = 'rejected'
    solicitud.rejection_reason = motivo
    solicitud.rechazo_definitivo = rechazo_definitivo
    solicitud.reviewed_by_id = current_user.id
    solicitud.reviewed_at = datetime.utcnow()
    
    tipeo_available = solicitud.tipeo_available
    if tipeo_available:
        if rechazo_definitivo:
            tipeo_available.status = 'expired'
        else:
            tipeo_available.status = 'available'
            tipeo_available.claimed_at = None
    
    # Solo crear notificación si hay viewer asociado
    if solicitud.viewer_id:
        if rechazo_definitivo:
            notificacion = UserNotification(
                viewer_id=solicitud.viewer_id,
                title='❌ Solicitud de tipeo rechazada definitivamente',
                message=f'Tu solicitud fue rechazada. Motivo: {motivo}. Esta decisión es definitiva.',
                notification_type='error'
            )
        else:
            notificacion = UserNotification(
                viewer_id=solicitud.viewer_id,
                title='❌ Solicitud de tipeo rechazada',
                message=f'Tu solicitud fue rechazada. Motivo: {motivo}. Puedes intentarlo nuevamente.',
                notification_type='warning'
            )
        db.session.add(notificacion)
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Tipeo rechazado' + (' definitivamente' if rechazo_definitivo else '')})


@tipeos_bp.route('/reenviar/<int:request_id>', methods=['POST'])
def reenviar_tipeo(request_id):
    """Usuario solicita reabrir un tipeo rechazado para corregirlo"""
    solicitud = TipeoRequest.query.get_or_404(request_id)
    
    if solicitud.status != 'rejected':
        return jsonify({'success': False, 'error': 'Solo puedes reenviar tipeos rechazados'}), 400
    
    # Bloquear si es rechazo definitivo
    if solicitud.rechazo_definitivo:
        return jsonify({'success': False, 'error': 'Esta solicitud fue rechazada definitivamente y no puede reenviarse'}), 400
    
    tipeo_available = solicitud.tipeo_available
    if not tipeo_available or tipeo_available.status != 'available':
        return jsonify({'success': False, 'error': 'Este tipeo ya no está disponible para reenvío'}), 400
    
    db.session.delete(solicitud)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Tipeo reabierto. Puedes enviar nuevamente tu solicitud.',
        'tipeo_id': tipeo_available.id
    })


@tipeos_bp.route('/enviar', methods=['POST'])
def enviar_solicitud():
    """Usuario envía su solicitud de tipeo con evidencia"""
    viewer_id = request.form.get('viewer_id')
    tipeo_id = request.form.get('tipeo_id')
    
    if not viewer_id or not tipeo_id:
        return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
    
    tipeo = TipeoAvailable.query.get_or_404(tipeo_id)
    
    if tipeo.status != 'available':
        return jsonify({'success': False, 'error': 'Este tipeo ya no está disponible'}), 400
    
    if str(tipeo.viewer_id) != str(viewer_id):
        return jsonify({'success': False, 'error': 'Este tipeo no te pertenece'}), 403
    
    nick_stake = request.form.get('nick_stake', '').strip()
    nick_kick = request.form.get('nick_kick', '').strip()
    red_crypto = request.form.get('red_crypto', 'TRX').strip()
    direccion_crypto = request.form.get('direccion_crypto', '').strip()
    instagram = request.form.get('instagram', '').strip()
    
    if not nick_stake or not nick_kick or not red_crypto or not direccion_crypto:
        return jsonify({'success': False, 'error': 'Completa todos los campos obligatorios'}), 400
    
    if 'image1' not in request.files or 'image2' not in request.files:
        return jsonify({'success': False, 'error': 'Debes subir las 2 imágenes de evidencia'}), 400
    
    image1 = request.files['image1']
    image2 = request.files['image2']
    
    if image1.filename == '' or image2.filename == '':
        return jsonify({'success': False, 'error': 'Debes seleccionar las 2 imágenes'}), 400
    
    if not allowed_file(image1.filename) or not allowed_file(image2.filename):
        return jsonify({'success': False, 'error': 'Formato de imagen no válido. Usa: PNG, JPG, JPEG, GIF o WEBP'}), 400
    
    unique_id = str(uuid.uuid4())[:8]
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    
    safe_filename1 = secure_filename(image1.filename)
    ext1 = safe_filename1.rsplit('.', 1)[1].lower() if '.' in safe_filename1 else 'jpg'
    object_key1 = f"tipeos/tipeo_{viewer_id}_{timestamp}_{unique_id}_1.{ext1}"
    
    safe_filename2 = secure_filename(image2.filename)
    ext2 = safe_filename2.rsplit('.', 1)[1].lower() if '.' in safe_filename2 else 'jpg'
    object_key2 = f"tipeos/tipeo_{viewer_id}_{timestamp}_{unique_id}_2.{ext2}"
    
    image1_data = image1.read()
    image2_data = image2.read()
    
    local_filename1 = f"tipeo_{viewer_id}_{timestamp}_{unique_id}_1.{ext1}"
    local_filename2 = f"tipeo_{viewer_id}_{timestamp}_{unique_id}_2.{ext2}"
    
    try:
        image_url_1 = save_image_to_storage(image1_data, local_filename1)
        image_url_2 = save_image_to_storage(image2_data, local_filename2)
    except Exception as e:
        logging.error(f"Error guardando imágenes: {e}")
        return jsonify({'success': False, 'error': 'Error al guardar imágenes'}), 500
    
    solicitud = TipeoRequest(
        tipeo_available_id=tipeo.id,
        viewer_id=int(viewer_id),
        nick_stake=nick_stake,
        nick_kick=nick_kick,
        red_crypto=red_crypto,
        direccion_crypto=direccion_crypto,
        instagram=instagram if instagram else None,
        image_url_1=image_url_1,
        image_url_2=image_url_2,
        status='submitted'
    )
    db.session.add(solicitud)
    
    tipeo.status = 'claimed'
    tipeo.claimed_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': '¡Solicitud enviada! Te notificaremos cuando sea procesada.'
    })


@tipeos_bp.route('/enviar-cuenta-nueva', methods=['POST'])
def enviar_solicitud_cuenta_nueva():
    """Usuario nuevo de Stake envía su solicitud de tipeo (con o sin sesión de Kick)"""
    from flask import session
    
    nick_kick = request.form.get('nick_kick', '').strip()
    
    if not nick_kick:
        return jsonify({'success': False, 'error': 'Debes proporcionar tu nick de Kick'}), 400
    
    # Intentar obtener viewer de la sesión o buscarlo/crearlo por nick_kick
    viewer_id = session.get('viewer_id')
    viewer = None
    
    if viewer_id:
        viewer = Viewer.query.get(viewer_id)
    
    if not viewer:
        # Buscar viewer por nick_kick (case insensitive)
        viewer = Viewer.query.filter(
            db.func.lower(Viewer.username_kick) == nick_kick.lower()
        ).first()
        
        if not viewer:
            # Crear nuevo viewer con los datos proporcionados
            viewer = Viewer(
                username_kick=nick_kick,
                points=0
            )
            db.session.add(viewer)
            db.session.flush()  # Para obtener el ID
    
    viewer_id = viewer.id
    
    # Verificar si ya tiene una solicitud de cuenta nueva pendiente
    solicitud_existente = TipeoRequest.query.join(TipeoAvailable).filter(
        TipeoAvailable.viewer_id == viewer_id,
        TipeoRequest.tipo_solicitud == 'cuenta_nueva',
        TipeoRequest.status.in_(['submitted'])
    ).first()
    
    if solicitud_existente:
        return jsonify({'success': False, 'error': 'Ya tienes una solicitud pendiente de revisión'}), 400
    
    # Verificar si fue rechazado definitivamente
    rechazado_definitivo = TipeoRequest.query.join(TipeoAvailable).filter(
        TipeoAvailable.viewer_id == viewer_id,
        TipeoRequest.tipo_solicitud == 'cuenta_nueva',
        TipeoRequest.rechazo_definitivo == True
    ).first()
    
    if rechazado_definitivo:
        return jsonify({'success': False, 'error': 'Tu solicitud fue rechazada definitivamente. No puedes enviar otra.'}), 400
    
    nick_stake = request.form.get('nick_stake', '').strip()
    nick_kick = request.form.get('nick_kick', '').strip()
    red_crypto = request.form.get('red_crypto', 'TRX').strip()
    direccion_crypto = request.form.get('direccion_crypto', '').strip()
    instagram = request.form.get('instagram', '').strip()
    
    if not nick_stake or not nick_kick or not direccion_crypto:
        return jsonify({'success': False, 'error': 'Completa todos los campos obligatorios'}), 400
    
    if 'image1' not in request.files or 'image2' not in request.files:
        return jsonify({'success': False, 'error': 'Debes subir las 2 imágenes de evidencia'}), 400
    
    image1 = request.files['image1']
    image2 = request.files['image2']
    
    if image1.filename == '' or image2.filename == '':
        return jsonify({'success': False, 'error': 'Debes seleccionar las 2 imágenes'}), 400
    
    if not allowed_file(image1.filename) or not allowed_file(image2.filename):
        return jsonify({'success': False, 'error': 'Formato de imagen no válido. Usa: PNG, JPG, JPEG, GIF o WEBP'}), 400
    
    # Crear TipeoAvailable automático para cuentas nuevas
    # Buscar el administrador (yangprroo) para asignar como granted_by
    admin_user = User.query.filter_by(email='yangprroo@gmail.com').first()
    granted_by = admin_user.id if admin_user else None
    
    tipeo = TipeoAvailable(
        viewer_id=viewer_id,
        granted_by_id=granted_by,
        status='claimed'
    )
    db.session.add(tipeo)
    db.session.flush()  # Para obtener el ID
    
    unique_id = str(uuid.uuid4())[:8]
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    
    safe_filename1 = secure_filename(image1.filename)
    ext1 = safe_filename1.rsplit('.', 1)[1].lower() if '.' in safe_filename1 else 'jpg'
    
    safe_filename2 = secure_filename(image2.filename)
    ext2 = safe_filename2.rsplit('.', 1)[1].lower() if '.' in safe_filename2 else 'jpg'
    
    image1_data = image1.read()
    image2_data = image2.read()
    
    local_filename1 = f"tipeo_{viewer_id}_{timestamp}_{unique_id}_1.{ext1}"
    local_filename2 = f"tipeo_{viewer_id}_{timestamp}_{unique_id}_2.{ext2}"
    
    try:
        image_url_1 = save_image_to_storage(image1_data, local_filename1)
        image_url_2 = save_image_to_storage(image2_data, local_filename2)
    except Exception as e:
        logging.error(f"Error guardando imágenes: {e}")
        return jsonify({'success': False, 'error': 'Error al guardar imágenes'}), 500
    
    solicitud = TipeoRequest(
        tipeo_available_id=tipeo.id,
        viewer_id=viewer_id,
        nick_stake=nick_stake,
        nick_kick=nick_kick,
        red_crypto=red_crypto,
        direccion_crypto=direccion_crypto,
        instagram=instagram if instagram else None,
        image_url_1=image_url_1,
        image_url_2=image_url_2,
        status='submitted',
        tipo_solicitud='cuenta_nueva'
    )
    db.session.add(solicitud)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': '¡Solicitud enviada! Revisaremos que tu cuenta sea nueva.'
    })


@tipeos_bp.route('/historial/<int:viewer_id>')
def historial_tipeos(viewer_id):
    """Obtener historial de tipeos de un viewer"""
    tipeos = TipeoRequest.query.filter_by(viewer_id=viewer_id).order_by(TipeoRequest.created_at.desc()).all()
    
    historial = []
    for t in tipeos:
        # No permitir reenviar si es rechazo definitivo
        can_retry = (t.status == 'rejected' and 
                    not t.rechazo_definitivo and 
                    t.tipeo_available and 
                    t.tipeo_available.status == 'available')
        historial.append({
            'id': t.id,
            'nick_stake': t.nick_stake,
            'status': t.status,
            'created_at': t.created_at.strftime('%d/%m/%Y %H:%M'),
            'reviewed_at': t.reviewed_at.strftime('%d/%m/%Y %H:%M') if t.reviewed_at else None,
            'rejection_reason': t.rejection_reason,
            'rechazo_definitivo': t.rechazo_definitivo,
            'can_retry': can_retry,
            'tipeo_available_id': t.tipeo_available_id if can_retry else None
        })
    
    return jsonify({'success': True, 'historial': historial})


@tipeos_bp.route('/disponible/<int:viewer_id>')
def check_tipeo_disponible(viewer_id):
    """Verificar si el viewer tiene un tipeo disponible"""
    tipeo = TipeoAvailable.query.filter_by(
        viewer_id=viewer_id,
        status='available'
    ).first()
    
    if tipeo:
        return jsonify({
            'disponible': True,
            'tipeo_id': tipeo.id,
            'created_at': tipeo.created_at.strftime('%d/%m/%Y %H:%M')
        })
    
    return jsonify({'disponible': False})


@tipeos_bp.route('/notificaciones/<int:viewer_id>')
def get_notificaciones(viewer_id):
    """Obtener notificaciones no leídas de un viewer"""
    notificaciones = UserNotification.query.filter_by(
        viewer_id=viewer_id,
        is_read=False
    ).order_by(UserNotification.created_at.desc()).all()
    
    result = []
    for n in notificaciones:
        result.append({
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'type': n.notification_type,
            'action_url': n.action_url,
            'created_at': n.created_at.strftime('%d/%m/%Y %H:%M')
        })
    
    return jsonify({'success': True, 'notificaciones': result, 'count': len(result)})


@tipeos_bp.route('/notificacion/leer/<int:notification_id>', methods=['POST'])
def marcar_leida(notification_id):
    """Marcar una notificación como leída"""
    notificacion = UserNotification.query.get_or_404(notification_id)
    notificacion.is_read = True
    notificacion.read_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'success': True})


@tipeos_bp.route('/admin/stats')
@login_required
def admin_stats():
    """Obtener estadísticas de tipeos para el panel admin"""
    if not is_streamer_or_admin():
        return jsonify({'success': False, 'error': 'Acceso denegado'}), 403
    
    tipeos_disponibles = TipeoAvailable.query.filter_by(status='available').count()
    solicitudes_pendientes = TipeoRequest.query.filter_by(status='submitted').count()
    solicitudes_completadas = TipeoRequest.query.filter_by(status='completed').count()
    solicitudes_rechazadas = TipeoRequest.query.filter_by(status='rejected').count()
    
    return jsonify({
        'success': True,
        'tipeos_disponibles': tipeos_disponibles,
        'solicitudes_pendientes': solicitudes_pendientes,
        'solicitudes_completadas': solicitudes_completadas,
        'solicitudes_rechazadas': solicitudes_rechazadas
    })


@tipeos_bp.route('/admin/vincular-retroactivo', methods=['POST'])
@login_required
def vincular_retroactivo():
    """Vincular retroactivamente las cuentas de Stake de tipeos ya aprobados"""
    if not is_streamer_or_admin():
        return jsonify({'success': False, 'error': 'Acceso denegado'}), 403
    
    solicitudes_completadas = TipeoRequest.query.filter_by(status='completed').all()
    
    vinculados = 0
    ya_vinculados = 0
    sin_stake = 0
    
    for solicitud in solicitudes_completadas:
        if not solicitud.nick_stake:
            sin_stake += 1
            continue
        
        viewer = solicitud.viewer
        if not viewer:
            continue
        
        if viewer.stake_username and viewer.stake_verified:
            ya_vinculados += 1
            continue
        
        viewer.stake_username = solicitud.nick_stake
        viewer.stake_verified = True
        vinculados += 1
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Proceso completado: {vinculados} vinculados, {ya_vinculados} ya estaban vinculados, {sin_stake} sin nick_stake',
        'vinculados': vinculados,
        'ya_vinculados': ya_vinculados,
        'sin_stake': sin_stake
    })


@tipeos_bp.route('/imagen/<path:filename>')
def servir_imagen(filename):
    """Sirve imágenes de tipeos desde Object Storage o local"""
    from flask import abort, Response
    import mimetypes
    
    local_filename = os.path.basename(filename)
    
    image_data = get_image_from_storage(local_filename)
    
    if image_data:
        content_type = mimetypes.guess_type(local_filename)[0] or 'image/jpeg'
        return Response(image_data, mimetype=content_type)
    
    return abort(404)


@tipeos_bp.route('/video/<path:filename>')
def servir_video(filename):
    """Sirve videos desde Object Storage o local"""
    from flask import abort, Response
    import mimetypes
    
    local_filename = os.path.basename(filename)
    object_key = f"videos/{local_filename}"
    
    if OBJECT_STORAGE_AVAILABLE and object_storage:
        try:
            data = object_storage.download_as_bytes(object_key)
            if data:
                content_type = mimetypes.guess_type(local_filename)[0] or 'video/mp4'
                return Response(data, mimetype=content_type)
        except Exception as e:
            logging.debug(f"Video not in Object Storage: {e}")
    
    local_path = os.path.join('static/videos', local_filename)
    if os.path.exists(local_path):
        with open(local_path, 'rb') as f:
            data = f.read()
        content_type = mimetypes.guess_type(local_filename)[0] or 'video/mp4'
        return Response(data, mimetype=content_type)
    
    return abort(404)
