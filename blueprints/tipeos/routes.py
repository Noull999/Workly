from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from . import tipeos_bp
from app import db
from models import TipeoAvailable, TipeoRequest, UserNotification, Viewer, User, RankPeriod, RankPeriodUser, StakeKickLink
from datetime import datetime
from blueprints.public.routes import get_wager_race_data
import os
import uuid

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
    if viewer and solicitud.nick_stake:
        viewer.stake_username = solicitud.nick_stake
        viewer.stake_verified = True
    
    notificacion = UserNotification(
        viewer_id=solicitud.viewer_id,
        title='✅ ¡Tu tipeo fue realizado!',
        message=f'Tu solicitud de tipeo ha sido aprobada. Tu cuenta de Stake ({solicitud.nick_stake}) ha sido vinculada automáticamente.',
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
    
    solicitud.status = 'rejected'
    solicitud.rejection_reason = motivo
    solicitud.reviewed_by_id = current_user.id
    solicitud.reviewed_at = datetime.utcnow()
    
    tipeo_available = solicitud.tipeo_available
    if tipeo_available:
        tipeo_available.status = 'available'
        tipeo_available.claimed_at = None
    
    notificacion = UserNotification(
        viewer_id=solicitud.viewer_id,
        title='❌ Solicitud de tipeo rechazada',
        message=f'Tu solicitud fue rechazada. Motivo: {motivo}. Puedes intentarlo nuevamente.',
        notification_type='warning'
    )
    db.session.add(notificacion)
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Tipeo rechazado'})


@tipeos_bp.route('/reenviar/<int:request_id>', methods=['POST'])
def reenviar_tipeo(request_id):
    """Usuario solicita reabrir un tipeo rechazado para corregirlo"""
    solicitud = TipeoRequest.query.get_or_404(request_id)
    
    if solicitud.status != 'rejected':
        return jsonify({'success': False, 'error': 'Solo puedes reenviar tipeos rechazados'}), 400
    
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
    red_crypto = request.form.get('red_crypto', '').strip()
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
    
    ensure_upload_folder()
    
    unique_id = str(uuid.uuid4())[:8]
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    
    safe_filename1 = secure_filename(image1.filename)
    ext1 = safe_filename1.rsplit('.', 1)[1].lower() if '.' in safe_filename1 else 'jpg'
    filename1 = f"tipeo_{viewer_id}_{timestamp}_{unique_id}_1.{ext1}"
    filepath1 = os.path.join(UPLOAD_FOLDER, filename1)
    image1.save(filepath1)
    
    safe_filename2 = secure_filename(image2.filename)
    ext2 = safe_filename2.rsplit('.', 1)[1].lower() if '.' in safe_filename2 else 'jpg'
    filename2 = f"tipeo_{viewer_id}_{timestamp}_{unique_id}_2.{ext2}"
    filepath2 = os.path.join(UPLOAD_FOLDER, filename2)
    image2.save(filepath2)
    
    solicitud = TipeoRequest(
        tipeo_available_id=tipeo.id,
        viewer_id=int(viewer_id),
        nick_stake=nick_stake,
        nick_kick=nick_kick,
        red_crypto=red_crypto,
        direccion_crypto=direccion_crypto,
        instagram=instagram if instagram else None,
        image_url_1=f'/{filepath1}',
        image_url_2=f'/{filepath2}',
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


@tipeos_bp.route('/historial/<int:viewer_id>')
def historial_tipeos(viewer_id):
    """Obtener historial de tipeos de un viewer"""
    tipeos = TipeoRequest.query.filter_by(viewer_id=viewer_id).order_by(TipeoRequest.created_at.desc()).all()
    
    historial = []
    for t in tipeos:
        can_retry = t.status == 'rejected' and t.tipeo_available and t.tipeo_available.status == 'available'
        historial.append({
            'id': t.id,
            'nick_stake': t.nick_stake,
            'status': t.status,
            'created_at': t.created_at.strftime('%d/%m/%Y %H:%M'),
            'reviewed_at': t.reviewed_at.strftime('%d/%m/%Y %H:%M') if t.reviewed_at else None,
            'rejection_reason': t.rejection_reason,
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
