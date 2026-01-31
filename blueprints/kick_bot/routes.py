from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from models import KickBotConfig, KickBotCommand, KickRaffle, KickRaffleParticipant, StreamerConfig
from datetime import datetime
from functools import wraps
import random
import json
import os
import hashlib
import hmac

from . import kick_bot

COMMAND_COOLDOWNS = {}

def get_bot_api_secret():
    """Obtener el secreto de API del bot desde variables de entorno"""
    return os.environ.get('KICK_BOT_API_SECRET', 'default-dev-secret')


def validate_api_request(f):
    """Decorador para validar requests de API del bot"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_secret = request.headers.get('X-Bot-Secret', '')
        expected_secret = get_bot_api_secret()
        
        if not hmac.compare_digest(api_secret, expected_secret):
            return jsonify({'error': 'Unauthorized'}), 401
        
        return f(*args, **kwargs)
    return decorated_function


def check_cooldown(config_id, command, cooldown_seconds):
    """Verificar si el comando está en cooldown"""
    key = f"{config_id}:{command}"
    now = datetime.utcnow()
    
    if key in COMMAND_COOLDOWNS:
        last_used = COMMAND_COOLDOWNS[key]
        diff = (now - last_used).total_seconds()
        if diff < cooldown_seconds:
            return False
    
    COMMAND_COOLDOWNS[key] = now
    return True


@kick_bot.route('/admin')
@login_required
def admin_panel():
    """Panel de administración del bot de Kick"""
    config = KickBotConfig.query.filter_by(streamer_email=current_user.email).first()
    
    if not config:
        config = KickBotConfig(
            streamer_email=current_user.email,
            channel_name=current_user.username,
            is_active=False
        )
        db.session.add(config)
        db.session.commit()
        
        default_commands = [
            ('comandos', 'Lista de comandos: !redes, !discord, !wager, !top, !sorteo'),
            ('redes', 'Sígueme en todas mis redes sociales'),
            ('discord', 'Únete a nuestro Discord: https://discord.gg/yanglee'),
        ]
        for cmd, resp in default_commands:
            command = KickBotCommand(
                config_id=config.id,
                command=cmd,
                response=resp
            )
            db.session.add(command)
        db.session.commit()
    
    commands = KickBotCommand.query.filter_by(config_id=config.id).all()
    raffles = KickRaffle.query.filter_by(config_id=config.id).order_by(KickRaffle.created_at.desc()).limit(10).all()
    active_raffle = KickRaffle.query.filter_by(config_id=config.id, is_active=True).first()
    
    return render_template('kick_bot/admin.html', 
                           config=config, 
                           commands=commands, 
                           raffles=raffles,
                           active_raffle=active_raffle)


@kick_bot.route('/config/update', methods=['POST'])
@login_required
def update_config():
    """Actualizar configuración del bot"""
    config = KickBotConfig.query.filter_by(streamer_email=current_user.email).first()
    if not config:
        flash('Configuración no encontrada', 'error')
        return redirect(url_for('kick_bot.admin_panel'))
    
    config.channel_name = request.form.get('channel_name', config.channel_name)
    config.channel_id = request.form.get('channel_id') or config.channel_id
    config.is_active = request.form.get('is_active') == 'on'
    
    db.session.commit()
    flash('Configuración actualizada correctamente', 'success')
    return redirect(url_for('kick_bot.admin_panel'))


@kick_bot.route('/command/add', methods=['POST'])
@login_required
def add_command():
    """Agregar nuevo comando"""
    config = KickBotConfig.query.filter_by(streamer_email=current_user.email).first()
    if not config:
        flash('Configuración no encontrada', 'error')
        return redirect(url_for('kick_bot.admin_panel'))
    
    command_name = request.form.get('command', '').strip().lower()
    response = request.form.get('response', '').strip()
    
    if not command_name or not response:
        flash('Comando y respuesta son requeridos', 'error')
        return redirect(url_for('kick_bot.admin_panel'))
    
    command_name = command_name.lstrip('!')
    
    existing = KickBotCommand.query.filter_by(config_id=config.id, command=command_name).first()
    if existing:
        flash(f'El comando !{command_name} ya existe', 'error')
        return redirect(url_for('kick_bot.admin_panel'))
    
    command = KickBotCommand(
        config_id=config.id,
        command=command_name,
        response=response,
        cooldown_seconds=int(request.form.get('cooldown', 5))
    )
    db.session.add(command)
    db.session.commit()
    
    flash(f'Comando !{command_name} creado correctamente', 'success')
    return redirect(url_for('kick_bot.admin_panel'))


@kick_bot.route('/command/<int:command_id>/delete', methods=['POST'])
@login_required
def delete_command(command_id):
    """Eliminar comando"""
    command = KickBotCommand.query.get_or_404(command_id)
    config = KickBotConfig.query.filter_by(streamer_email=current_user.email).first()
    
    if command.config_id != config.id:
        flash('No tienes permiso para eliminar este comando', 'error')
        return redirect(url_for('kick_bot.admin_panel'))
    
    db.session.delete(command)
    db.session.commit()
    
    flash(f'Comando !{command.command} eliminado', 'success')
    return redirect(url_for('kick_bot.admin_panel'))


@kick_bot.route('/command/<int:command_id>/edit', methods=['POST'])
@login_required
def edit_command(command_id):
    """Editar comando existente"""
    command = KickBotCommand.query.get_or_404(command_id)
    config = KickBotConfig.query.filter_by(streamer_email=current_user.email).first()
    
    if command.config_id != config.id:
        flash('No autorizado', 'error')
        return redirect(url_for('kick_bot.admin_panel'))
    
    command.response = request.form.get('response', command.response)
    command.cooldown_seconds = int(request.form.get('cooldown', 5))
    command.is_active = request.form.get('is_active') == 'on'
    
    db.session.commit()
    flash(f'Comando !{command.command} actualizado', 'success')
    return redirect(url_for('kick_bot.admin_panel'))


@kick_bot.route('/raffle/create', methods=['POST'])
@login_required
def create_raffle():
    """Crear nuevo sorteo"""
    config = KickBotConfig.query.filter_by(streamer_email=current_user.email).first()
    if not config:
        flash('Configuración no encontrada', 'error')
        return redirect(url_for('kick_bot.admin_panel'))
    
    active = KickRaffle.query.filter_by(config_id=config.id, is_active=True).first()
    if active:
        flash('Ya hay un sorteo activo. Finálizalo primero.', 'error')
        return redirect(url_for('kick_bot.admin_panel'))
    
    raffle = KickRaffle(
        config_id=config.id,
        title=request.form.get('title', 'Sorteo'),
        prize=request.form.get('prize', 'Premio'),
        keyword=request.form.get('keyword', 'participar').lower(),
        is_active=True,
        started_at=datetime.utcnow()
    )
    db.session.add(raffle)
    db.session.commit()
    
    flash(f'Sorteo "{raffle.title}" iniciado. Los usuarios pueden participar con !{raffle.keyword}', 'success')
    return redirect(url_for('kick_bot.admin_panel'))


@kick_bot.route('/raffle/<int:raffle_id>/end', methods=['POST'])
@login_required
def end_raffle(raffle_id):
    """Finalizar sorteo y elegir ganador"""
    raffle = KickRaffle.query.get_or_404(raffle_id)
    config = KickBotConfig.query.filter_by(streamer_email=current_user.email).first()
    
    if raffle.config_id != config.id:
        flash('No autorizado', 'error')
        return redirect(url_for('kick_bot.admin_panel'))
    
    participants = KickRaffleParticipant.query.filter_by(raffle_id=raffle.id).all()
    
    if participants:
        winner = random.choice(participants)
        raffle.winner_username = winner.username
    else:
        raffle.winner_username = None
    
    raffle.is_active = False
    raffle.ended_at = datetime.utcnow()
    db.session.commit()
    
    if raffle.winner_username:
        flash(f'Sorteo finalizado. Ganador: {raffle.winner_username}', 'success')
    else:
        flash('Sorteo finalizado sin participantes.', 'warning')
    
    return redirect(url_for('kick_bot.admin_panel'))


@kick_bot.route('/raffle/<int:raffle_id>/participants')
@login_required
def raffle_participants(raffle_id):
    """Ver participantes de un sorteo"""
    raffle = KickRaffle.query.get_or_404(raffle_id)
    config = KickBotConfig.query.filter_by(streamer_email=current_user.email).first()
    
    if raffle.config_id != config.id:
        return jsonify({'error': 'No autorizado'}), 403
    
    participants = KickRaffleParticipant.query.filter_by(raffle_id=raffle.id).all()
    return jsonify({
        'raffle': raffle.title,
        'count': len(participants),
        'participants': [p.username for p in participants]
    })


@kick_bot.route('/api/command-response', methods=['POST'])
@validate_api_request
def command_response():
    """API endpoint para consultar respuestas a comandos (usado por bot externo o webhook)
    
    Requiere header: X-Bot-Secret con el secreto configurado en KICK_BOT_API_SECRET
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    
    channel = data.get('channel', '').lower()
    command = data.get('command', '').lower().lstrip('!')
    username = data.get('username', '')
    
    if not channel or not command:
        return jsonify({'error': 'Missing channel or command'}), 400
    
    if not username:
        return jsonify({'error': 'Missing username'}), 400
    
    config = KickBotConfig.query.filter(
        db.func.lower(KickBotConfig.channel_name) == channel,
        KickBotConfig.is_active == True
    ).first()
    
    if not config:
        return jsonify({'response': None})
    
    if command == 'wager' or command == 'top':
        if not check_cooldown(config.id, command, 10):
            return jsonify({'response': None, 'cooldown': True})
        return get_wager_response(config, command, username)
    
    if command == 'sorteo':
        if not check_cooldown(config.id, command, 5):
            return jsonify({'response': None, 'cooldown': True})
        return get_raffle_info(config)
    
    active_raffle = KickRaffle.query.filter_by(config_id=config.id, is_active=True).first()
    if active_raffle and command == active_raffle.keyword:
        return join_raffle(active_raffle, username)
    
    cmd = KickBotCommand.query.filter_by(
        config_id=config.id,
        command=command,
        is_active=True
    ).first()
    
    if cmd:
        if not check_cooldown(config.id, command, cmd.cooldown_seconds):
            return jsonify({'response': None, 'cooldown': True})
        
        cmd.use_count += 1
        cmd.last_used_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'response': cmd.response})
    
    return jsonify({'response': None})


def get_wager_response(config, command, username):
    """Obtener respuesta de wager race"""
    streamer_config = StreamerConfig.query.filter_by(streamer_email=config.streamer_email).first()
    
    if not streamer_config or not streamer_config.wager_race_json:
        return jsonify({'response': 'No hay datos de wager race disponibles.'})
    
    try:
        wager_data = json.loads(streamer_config.wager_race_json) if isinstance(streamer_config.wager_race_json, str) else streamer_config.wager_race_json
        current_data = wager_data.get('current', [])
        
        if command == 'top':
            if current_data:
                top_3 = current_data[:3]
                response = "Top 3 Wager Race: "
                for i, player in enumerate(top_3, 1):
                    response += f"#{i} {player['username']} (${player['wagered']:,.0f}) "
                return jsonify({'response': response.strip()})
            return jsonify({'response': 'No hay datos de wager race.'})
        
        if command == 'wager' and username:
            user_entry = next((p for p in current_data if p['username'].lower() == username.lower()), None)
            if user_entry:
                response = f"@{username} estás en el puesto #{user_entry['rank']} con ${user_entry['wagered']:,.2f} apostados."
                return jsonify({'response': response})
            return jsonify({'response': f"@{username} no estás en el leaderboard de la wager race."})
        
    except Exception as e:
        print(f"Error getting wager data: {e}")
        return jsonify({'response': 'Error al obtener datos de wager race.'})
    
    return jsonify({'response': None})


def get_raffle_info(config):
    """Obtener información del sorteo activo"""
    active = KickRaffle.query.filter_by(config_id=config.id, is_active=True).first()
    
    if active:
        participant_count = KickRaffleParticipant.query.filter_by(raffle_id=active.id).count()
        return jsonify({
            'response': f'Sorteo activo: "{active.title}" - Premio: {active.prize} - Participantes: {participant_count} - Escribe !{active.keyword} para participar'
        })
    
    return jsonify({'response': 'No hay sorteos activos en este momento.'})


def join_raffle(raffle, username):
    """Unirse a un sorteo"""
    existing = KickRaffleParticipant.query.filter_by(
        raffle_id=raffle.id,
        username=username
    ).first()
    
    if existing:
        return jsonify({'response': f'@{username} ya estás participando en el sorteo.'})
    
    participant = KickRaffleParticipant(
        raffle_id=raffle.id,
        username=username
    )
    db.session.add(participant)
    db.session.commit()
    
    count = KickRaffleParticipant.query.filter_by(raffle_id=raffle.id).count()
    return jsonify({'response': f'@{username} te has unido al sorteo. Participantes: {count}'})


@kick_bot.route('/api/commands/<channel>')
def get_commands(channel):
    """API para obtener lista de comandos de un canal"""
    config = KickBotConfig.query.filter(
        db.func.lower(KickBotConfig.channel_name) == channel.lower(),
        KickBotConfig.is_active == True
    ).first()
    
    if not config:
        return jsonify({'commands': []})
    
    commands = KickBotCommand.query.filter_by(config_id=config.id, is_active=True).all()
    
    system_commands = ['!wager', '!top', '!sorteo']
    custom_commands = [f'!{cmd.command}' for cmd in commands]
    
    return jsonify({
        'channel': channel,
        'commands': system_commands + custom_commands
    })
