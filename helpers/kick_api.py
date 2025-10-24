"""
Helper para interactuar con la API de Kick.com
Proporciona funciones para obtener datos de canales sin necesidad de autenticación
"""
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

# Cache simple en memoria (en producción usar Redis)
_channel_cache = {}
_cache_duration = timedelta(minutes=5)

def get_channel_data(username: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """
    Obtiene datos públicos de un canal de Kick
    
    Args:
        username: Username del canal de Kick
        use_cache: Si usar cache (default True)
    
    Returns:
        Dict con datos del canal o None si hay error
    """
    cache_key = f"channel:{username}"
    
    # Verificar cache
    if use_cache and cache_key in _channel_cache:
        cached_data, cached_time = _channel_cache[cache_key]
        if datetime.now() - cached_time < _cache_duration:
            return cached_data
    
    try:
        # API pública de Kick (no requiere autenticación)
        response = requests.get(
            f'https://kick.com/api/v2/channels/{username}',
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Guardar en cache
            _channel_cache[cache_key] = (data, datetime.now())
            
            return data
        else:
            print(f"Error al obtener datos del canal {username}: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"Excepción al obtener datos del canal {username}: {str(e)}")
        return None

def get_stream_status(username: str) -> Dict[str, Any]:
    """
    Obtiene el estado actual del stream
    
    Returns:
        Dict con:
        - is_live: bool
        - viewer_count: int
        - title: str
        - thumbnail: str
        - started_at: datetime
    """
    data = get_channel_data(username)
    
    if not data:
        return {
            'is_live': False,
            'viewer_count': 0,
            'title': '',
            'thumbnail': '',
            'started_at': None,
            'error': True
        }
    
    livestream = data.get('livestream')
    
    if not livestream:
        return {
            'is_live': False,
            'viewer_count': 0,
            'title': '',
            'thumbnail': '',
            'started_at': None,
            'error': False
        }
    
    return {
        'is_live': livestream.get('is_live', False),
        'viewer_count': livestream.get('viewer_count', 0),
        'title': livestream.get('session_title', ''),
        'thumbnail': livestream.get('thumbnail', {}).get('url', ''),
        'started_at': livestream.get('created_at'),
        'error': False
    }

def get_channel_info(username: str) -> Dict[str, Any]:
    """
    Obtiene información general del canal
    
    Returns:
        Dict con:
        - username: str
        - display_name: str
        - bio: str
        - profile_pic: str
        - banner: str
        - follower_count: int
        - subscriber_count: int (si está disponible)
    """
    data = get_channel_data(username)
    
    if not data:
        return {
            'username': username,
            'display_name': username,
            'bio': '',
            'profile_pic': '',
            'banner': '',
            'follower_count': 0,
            'subscriber_count': 0,
            'error': True
        }
    
    return {
        'username': data.get('slug', username),
        'display_name': data.get('user', {}).get('username', username),
        'bio': data.get('user', {}).get('bio', ''),
        'profile_pic': data.get('user', {}).get('profile_pic', ''),
        'banner': data.get('banner', {}).get('url', ''),
        'follower_count': data.get('followers_count', 0),
        'subscriber_count': data.get('subscribers_count', 0),
        'error': False
    }

def clear_cache(username: Optional[str] = None):
    """
    Limpia el cache
    
    Args:
        username: Si se especifica, solo limpia ese canal. Si es None, limpia todo.
    """
    global _channel_cache
    
    if username:
        cache_key = f"channel:{username}"
        _channel_cache.pop(cache_key, None)
    else:
        _channel_cache = {}

def format_viewer_count(count: int) -> str:
    """
    Formatea el número de viewers de forma legible
    
    Args:
        count: Número de viewers
    
    Returns:
        String formateado (ej: "1.2K", "15.3K", "120")
    """
    if count >= 1000000:
        return f"{count / 1000000:.1f}M"
    elif count >= 1000:
        return f"{count / 1000:.1f}K"
    else:
        return str(count)
