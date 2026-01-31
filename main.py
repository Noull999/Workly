from app import app  # noqa: F401
import os
import threading
import time

def start_kick_bot():
    """Inicia el bot de Kick en un hilo separado"""
    time.sleep(5)
    
    try:
        from kick_chat_bot import KickChatBot
        import logging
        
        logger = logging.getLogger('KickChatBot')
        channel = os.environ.get('KICK_CHANNEL_USERNAME', 'yanglee')
        
        logger.info(f"Iniciando bot de Kick para canal: {channel}")
        bot = KickChatBot(channel)
        bot.start()
    except Exception as e:
        import logging
        logging.error(f"Error iniciando bot de Kick: {e}")

if os.environ.get('REPL_SLUG'):
    bot_thread = threading.Thread(target=start_kick_bot, daemon=True)
    bot_thread.start()
