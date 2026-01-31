from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from models import TwitchBotConfig, TwitchBotCommand, TwitchRaffle, TwitchRaffleParticipant, StreamerConfig
from datetime import datetime
import random
import json
import os

from . import twitch_bot


@twitch_bot.route('/admin')
@login_required
def admin_panel():
    """Panel de administración del bot de Twitch"""
    config = TwitchBotConfig.query.filter_by(streamer_email=current_user.email).first()
    
    if not config:
        config = TwitchBotConfig(
            streamer_email=current_user.email,
            channel_name=current_user.username,
            is_active=False
        )
        db.session.add(config)
        db.session.commit()
        
        default_commands = [
            ('comandos', 'Lista de comandos: !redes, !discord, !wager, !top, !sorteo'),
            ('redes', 'Sígueme en todas mis redes: Twitter, Instagram, TikTok'),
            ('discord', 'Únete a nuestro Discord: https://discord.gg/yanglee'),
        ]
        for cmd, resp in default_commands:
            command = TwitchBotCommand(
                config_id=config.id,
                command=cmd,
                response=resp
            )
            db.session.add(command)
        db.session.commit()
    
    commands = TwitchBotCommand.query.filter_by(config_id=config.id).all()
    raffles = TwitchRaffle.query.filter_by(config_id=config.id).order_by(TwitchRaffle.created_at.desc()).limit(10).all()
    active_raffle = TwitchRaffle.query.filter_by(config_id=config.id, is_active=True).first()
    
    return render_template('twitch_bot/admin.html', 
                           config=config, 
                           commands=commands, 
                           raffles=raffles,
                           active_raffle=active_raffle)


@twitch_bot.route('/config/update', methods=['POST'])
@login_required
def update_config():
    """Actualizar configuración del bot"""
    config = TwitchBotConfig.query.filter_by(streamer_email=current_user.email).first()
    if not config:
        flash('Configuración no encontrada', 'error')
        return redirect(url_for('twitch_bot.admin_panel'))
    
    config.channel_name = request.form.get('channel_name', config.channel_name)
    config.is_active = request.form.get('is_active') == 'on'
    config.oauth_token = request.form.get('oauth_token') or config.oauth_token
    
    db.session.commit()
    flash('Configuración actualizada correctamente', 'success')
    return redirect(url_for('twitch_bot.admin_panel'))


@twitch_bot.route('/command/add', methods=['POST'])
@login_required
def add_command():
    """Agregar nuevo comando"""
    config = TwitchBotConfig.query.filter_by(streamer_email=current_user.email).first()
    if not config:
        flash('Configuración no encontrada', 'error')
        return redirect(url_for('twitch_bot.admin_panel'))
    
    command_name = request.form.get('command', '').strip().lower()
    response = request.form.get('response', '').strip()
    
    if not command_name or not response:
        flash('Comando y respuesta son requeridos', 'error')
        return redirect(url_for('twitch_bot.admin_panel'))
    
    command_name = command_name.lstrip('!')
    
    existing = TwitchBotCommand.query.filter_by(config_id=config.id, command=command_name).first()
    if existing:
        flash(f'El comando !{command_name} ya existe', 'error')
        return redirect(url_for('twitch_bot.admin_panel'))
    
    command = TwitchBotCommand(
        config_id=config.id,
        command=command_name,
        response=response,
        cooldown_seconds=int(request.form.get('cooldown', 5))
    )
    db.session.add(command)
    db.session.commit()
    
    flash(f'Comando !{command_name} creado correctamente', 'success')
    return redirect(url_for('twitch_bot.admin_panel'))


@twitch_bot.route('/command/<int:command_id>/delete', methods=['POST'])
@login_required
def delete_command(command_id):
    """Eliminar comando"""
    command = TwitchBotCommand.query.get_or_404(command_id)
    config = TwitchBotConfig.query.filter_by(streamer_email=current_user.email).first()
    
    if command.config_id != config.id:
        flash('No tienes permiso para eliminar este comando', 'error')
        return redirect(url_for('twitch_bot.admin_panel'))
    
    db.session.delete(command)
    db.session.commit()
    
    flash(f'Comando !{command.command} eliminado', 'success')
    return redirect(url_for('twitch_bot.admin_panel'))


@twitch_bot.route('/command/<int:command_id>/toggle', methods=['POST'])
@login_required
def toggle_command(command_id):
    """Activar/desactivar comando"""
    command = TwitchBotCommand.query.get_or_404(command_id)
    config = TwitchBotConfig.query.filter_by(streamer_email=current_user.email).first()
    
    if command.config_id != config.id:
        return jsonify({'error': 'No autorizado'}), 403
    
    command.is_active = not command.is_active
    db.session.commit()
    
    return jsonify({'success': True, 'is_active': command.is_active})


@twitch_bot.route('/raffle/create', methods=['POST'])
@login_required
def create_raffle():
    """Crear nuevo sorteo"""
    config = TwitchBotConfig.query.filter_by(streamer_email=current_user.email).first()
    if not config:
        flash('Configuración no encontrada', 'error')
        return redirect(url_for('twitch_bot.admin_panel'))
    
    active = TwitchRaffle.query.filter_by(config_id=config.id, is_active=True).first()
    if active:
        flash('Ya hay un sorteo activo. Finálizalo primero.', 'error')
        return redirect(url_for('twitch_bot.admin_panel'))
    
    raffle = TwitchRaffle(
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
    return redirect(url_for('twitch_bot.admin_panel'))


@twitch_bot.route('/raffle/<int:raffle_id>/end', methods=['POST'])
@login_required
def end_raffle(raffle_id):
    """Finalizar sorteo y elegir ganador"""
    raffle = TwitchRaffle.query.get_or_404(raffle_id)
    config = TwitchBotConfig.query.filter_by(streamer_email=current_user.email).first()
    
    if raffle.config_id != config.id:
        flash('No autorizado', 'error')
        return redirect(url_for('twitch_bot.admin_panel'))
    
    participants = TwitchRaffleParticipant.query.filter_by(raffle_id=raffle.id).all()
    
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
    
    return redirect(url_for('twitch_bot.admin_panel'))


@twitch_bot.route('/api/bot-response', methods=['POST'])
def bot_response():
    """API endpoint para que el bot consulte respuestas a comandos"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    
    channel = data.get('channel', '').lower()
    command = data.get('command', '').lower().lstrip('!')
    username = data.get('username', '')
    
    config = TwitchBotConfig.query.filter(
        db.func.lower(TwitchBotConfig.channel_name) == channel,
        TwitchBotConfig.is_active == True
    ).first()
    
    if not config:
        return jsonify({'response': None})
    
    if command == 'wager' or command == 'top':
        return get_wager_response(config, command, username)
    
    if command == 'sorteo':
        return get_raffle_info(config)
    
    active_raffle = TwitchRaffle.query.filter_by(config_id=config.id, is_active=True).first()
    if active_raffle and command == active_raffle.keyword:
        return join_raffle(active_raffle, username)
    
    cmd = TwitchBotCommand.query.filter_by(
        config_id=config.id,
        command=command,
        is_active=True
    ).first()
    
    if cmd:
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
    active = TwitchRaffle.query.filter_by(config_id=config.id, is_active=True).first()
    
    if active:
        participant_count = TwitchRaffleParticipant.query.filter_by(raffle_id=active.id).count()
        return jsonify({
            'response': f'Sorteo activo: "{active.title}" - Premio: {active.prize} - Participantes: {participant_count} - Escribe !{active.keyword} para participar'
        })
    
    return jsonify({'response': 'No hay sorteos activos en este momento.'})


def join_raffle(raffle, username):
    """Unirse a un sorteo"""
    existing = TwitchRaffleParticipant.query.filter_by(
        raffle_id=raffle.id,
        username=username
    ).first()
    
    if existing:
        return jsonify({'response': f'@{username} ya estás participando en el sorteo.'})
    
    participant = TwitchRaffleParticipant(
        raffle_id=raffle.id,
        username=username
    )
    db.session.add(participant)
    db.session.commit()
    
    count = TwitchRaffleParticipant.query.filter_by(raffle_id=raffle.id).count()
    return jsonify({'response': f'@{username} te has unido al sorteo. Participantes: {count}'})
