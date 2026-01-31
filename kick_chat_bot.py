#!/usr/bin/env python3
"""
Bot de Chat para Kick.com
Se conecta al chat de Kick usando Pusher WebSockets y responde a comandos.
"""

import os
import json
import logging
import requests
import time
import threading
from datetime import datetime

import pysher

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('KickChatBot')

KICK_PUSHER_KEY = "32cbd69e4b950bf97679"
KICK_PUSHER_CLUSTER = "us2"

def get_api_base_url():
    """Detecta la URL base de la API automáticamente
    
    Cuando el bot corre en el mismo servidor que la app Flask,
    siempre usamos localhost para evitar problemas de DNS.
    """
    if os.environ.get('API_BASE_URL'):
        return os.environ.get('API_BASE_URL')
    
    return 'http://localhost:5000'

API_BASE_URL = get_api_base_url()
BOT_API_SECRET = os.environ.get('KICK_BOT_API_SECRET')
if not BOT_API_SECRET:
    logger.warning("KICK_BOT_API_SECRET no configurado - usando modo desarrollo")
    BOT_API_SECRET = 'default-dev-secret'

CHANNEL_USERNAME = os.environ.get('KICK_CHANNEL_USERNAME', 'yanglee')


class KickChatBot:
    def __init__(self, channel_username):
        self.channel_username = channel_username.lower()
        self.chatroom_id = None
        self.pusher = None
        self.connected = False
        self.channel = None
        
    def get_chatroom_id(self):
        """Obtener el ID del chatroom desde la API de Kick"""
        try:
            url = f"https://kick.com/api/v2/channels/{self.channel_username}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self.chatroom_id = data.get('chatroom', {}).get('id')
                logger.info(f"Chatroom ID obtenido: {self.chatroom_id}")
                return self.chatroom_id
            else:
                logger.error(f"Error obteniendo chatroom: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error al obtener chatroom ID: {e}")
            return None
    
    def process_command(self, username, message_text):
        """Procesar un comando y obtener respuesta de nuestra API"""
        if not message_text.startswith('!'):
            return None
        
        command = message_text.split()[0].lower()
        
        try:
            url = f"{API_BASE_URL}/kick-bot/api/command-response"
            headers = {
                'Content-Type': 'application/json',
                'X-Bot-Secret': BOT_API_SECRET
            }
            payload = {
                'channel': self.channel_username,
                'command': command,
                'username': username
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                bot_response = data.get('response')
                cooldown = data.get('cooldown', False)
                
                if cooldown:
                    logger.debug(f"Comando {command} en cooldown")
                    return None
                
                if bot_response:
                    logger.info(f"Respuesta para {command}: {bot_response[:50]}...")
                    return bot_response
            else:
                logger.error(f"Error de API: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error procesando comando: {e}")
        
        return None
    
    def send_chat_message(self, message):
        """Enviar mensaje al chat de Kick
        
        NOTA: Para enviar mensajes al chat de Kick se requiere:
        1. Registro de aplicación en https://dev.kick.com
        2. OAuth con scope 'chat:write'
        3. Access token válido
        
        Por ahora, las respuestas se registran en logs.
        Integra con un sistema externo para enviar al chat.
        """
        logger.info(f"[BOT RESPONSE] {message}")
        
        webhook_url = os.environ.get('KICK_RESPONSE_WEBHOOK')
        if webhook_url:
            try:
                requests.post(webhook_url, json={
                    'channel': self.channel_username,
                    'message': message
                }, timeout=5)
            except Exception as e:
                logger.error(f"Error enviando a webhook: {e}")
    
    def on_message(self, data):
        """Callback cuando se recibe un mensaje del chat"""
        try:
            if isinstance(data, str):
                data = json.loads(data)
            
            message_content = data.get('content', '')
            sender_data = data.get('sender', {})
            username = sender_data.get('username', 'Unknown')
            
            logger.debug(f"[{username}]: {message_content}")
            
            if message_content.startswith('!'):
                logger.info(f"Comando detectado de {username}: {message_content}")
                response = self.process_command(username, message_content)
                
                if response:
                    self.send_chat_message(response)
                    
        except Exception as e:
            logger.error(f"Error procesando mensaje: {e}")
    
    def on_connect(self, data):
        """Callback cuando se establece conexión con Pusher"""
        logger.info("Conectado a Pusher!")
        self.connected = True
        
        if self.chatroom_id:
            channel_name = f"chatrooms.{self.chatroom_id}.v2"
            logger.info(f"Suscribiéndose a: {channel_name}")
            
            self.channel = self.pusher.subscribe(channel_name)
            self.channel.bind('App\\Events\\ChatMessageEvent', self.on_message)
            
            logger.info(f"Bot escuchando chat de {self.channel_username}")
    
    def on_disconnect(self, data=None):
        """Callback cuando se desconecta"""
        logger.warning("Desconectado de Pusher")
        self.connected = False
    
    def on_subscription_error(self, data=None):
        """Callback para errores de suscripción"""
        logger.error(f"Error de suscripción: {data}")
        self.connected = False
    
    def on_error(self, error):
        """Callback para errores"""
        logger.error(f"Error de Pusher: {error}")
    
    def start(self):
        """Iniciar el bot"""
        logger.info(f"Iniciando bot para canal: {self.channel_username}")
        
        if not self.get_chatroom_id():
            logger.error("No se pudo obtener el chatroom ID. Reintentando en 30 segundos...")
            time.sleep(30)
            return self.start()
        
        self.pusher = pysher.Pusher(
            key=KICK_PUSHER_KEY,
            cluster=KICK_PUSHER_CLUSTER,
            daemon=False
        )
        
        self.pusher.connection.bind('pusher:connection_established', self.on_connect)
        self.pusher.connection.bind('pusher:connection_failed', self.on_error)
        self.pusher.connection.bind('pusher:error', self.on_error)
        self.pusher.connection.bind('pusher:disconnected', self.on_disconnect)
        
        logger.info("Conectando a Kick via Pusher...")
        self.pusher.connect()
        
        reconnect_attempts = 0
        max_reconnect_delay = 60
        
        while True:
            time.sleep(1)
            
            if not self.connected:
                reconnect_attempts += 1
                delay = min(5 * reconnect_attempts, max_reconnect_delay)
                logger.warning(f"Conexión perdida, reconectando en {delay}s (intento {reconnect_attempts})...")
                time.sleep(delay)
                
                try:
                    self.pusher = pysher.Pusher(
                        key=KICK_PUSHER_KEY,
                        cluster=KICK_PUSHER_CLUSTER,
                        daemon=False
                    )
                    self.pusher.connection.bind('pusher:connection_established', self.on_connect)
                    self.pusher.connection.bind('pusher:connection_failed', self.on_error)
                    self.pusher.connect()
                except Exception as e:
                    logger.error(f"Error reconectando: {e}")
            else:
                reconnect_attempts = 0


def main():
    channel = CHANNEL_USERNAME
    logger.info("=" * 50)
    logger.info("KICK CHAT BOT")
    logger.info("=" * 50)
    logger.info(f"Canal: {channel}")
    logger.info(f"API URL: {API_BASE_URL}")
    logger.info("=" * 50)
    
    bot = KickChatBot(channel)
    
    try:
        bot.start()
    except KeyboardInterrupt:
        logger.info("Bot detenido por el usuario")
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        time.sleep(10)
        main()


if __name__ == '__main__':
    main()
