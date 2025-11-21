from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from functools import wraps
from . import demos_bp

def admin_global_required(f):
    """Decorator para requerir admin_global"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin_global():
            flash('Acceso denegado. Solo súper administradores pueden acceder a las demos.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


@demos_bp.route('/')
@login_required
@admin_global_required
def index():
    """Página índice de demos disponibles"""
    demos = [
        {
            'title': 'Demo Módulo Streamer',
            'description': 'Página pública para streamers con sorteos, sistema de puntos Kick, Wager Race y clips destacados',
            'icon': 'fa-twitch',
            'color': 'purple',
            'url': url_for('demos.streamer_demo'),
            'features': [
                'Sorteos activos con participación',
                'Sistema de puntos automático (watchtime + visitas diarias)',
                'Wager Race de Stake.com',
                'Clips destacados',
                'Redes sociales y beneficios',
                'Diseño gaming moderno'
            ]
        },
        # Aquí se pueden agregar más demos en el futuro
    ]
    
    return render_template('demos/index.html', demos=demos)


@demos_bp.route('/streamer')
@login_required
@admin_global_required
def streamer_demo():
    """Demo del módulo streamer con datos ficticios"""
    
    # Datos ficticios del streamer
    page_data = {
        'title': 'Página oficial de DemoStreamer',
        'primary_color': '#ff6600',
        'secondary_color': '#1a1a1a',
        'profile_image_url': None,
        'banner_image_url': None,
        'social_links': {
            'kick': 'https://kick.com/demostreamer',
            'youtube': 'https://youtube.com/@demostreamer',
            'instagram': 'https://instagram.com/demostreamer',
            'whatsapp': '56912345678'
        }
    }
    
    # Usuario demo
    usuario_json = {
        'nombre': 'DemoStreamer',
        'descripcion': 'Streamer profesional de casino y gaming. ¡Únete a la comunidad!',
        'codigo_promocional': 'DEMO2024',
        'casino': 'https://stake.com',
        'kick_username': 'demostreamer'
    }
    
    # Sorteos activos de demostración
    sorteos_activos = [
        {
            'id': 1,
            'title': 'Sorteo Semanal PS5',
            'description': 'PlayStation 5 Digital Edition + 2 juegos a elección',
            'prize': 'PlayStation 5 + 2 Juegos',
            'entry_cost': 500,
            'is_active': True,
            'end_date': None,
            'entry_count': 127
        },
        {
            'id': 2,
            'title': 'Sorteo Diario $50 USD',
            'description': 'Sorteo rápido de $50 USD en efectivo vía PayPal',
            'prize': '$50 USD PayPal',
            'entry_cost': 100,
            'is_active': True,
            'end_date': None,
            'entry_count': 89
        },
        {
            'id': 3,
            'title': 'Mega Sorteo iPhone 15 Pro',
            'description': 'iPhone 15 Pro Max 256GB - Color a elección del ganador',
            'prize': 'iPhone 15 Pro Max 256GB',
            'entry_cost': 1000,
            'is_active': True,
            'end_date': None,
            'entry_count': 234
        }
    ]
    
    # Últimos sorteos completados
    ultimos_sorteos = [
        {
            'id': 4,
            'title': 'Sorteo AirPods Pro',
            'prize': 'AirPods Pro 2da Gen',
            'is_active': False,
            'winner_viewer': {
                'username_kick': 'WinnerUser123'
            }
        },
        {
            'id': 5,
            'title': 'Sorteo $100 Stake',
            'prize': '$100 USD Stake',
            'is_active': False,
            'winner_viewer': {
                'username_kick': 'LuckyGamer99'
            }
        }
    ]
    
    # Códigos canjeables activos
    codigos_activos = [
        {
            'code': 'BIENVENIDA',
            'points': 200,
            'description': 'Código de bienvenida para nuevos viewers'
        },
        {
            'code': 'STREAM100',
            'points': 100,
            'description': 'Código especial del stream'
        }
    ]
    
    # Configuración de puntos
    points_config = {
        'points_per_minute_watching': 10,
        'daily_visit_points': 100,
        'cooldown_seconds': 60
    }
    
    # Wager Race data
    wager_race_data = [
        {'rank': 1, 'username': 'HighRoller99', 'wagered': 125000.50, 'profit': 15230.75},
        {'rank': 2, 'username': 'CasinoKing', 'wagered': 98500.25, 'profit': -5420.30},
        {'rank': 3, 'username': 'LuckySpins', 'wagered': 87300.00, 'profit': 8950.00},
        {'rank': 4, 'username': 'MegaBetter', 'wagered': 76200.80, 'profit': 12100.50},
        {'rank': 5, 'username': 'SlotMaster', 'wagered': 65400.00, 'profit': -3200.00},
        {'rank': 6, 'username': 'DiceRoller', 'wagered': 58900.50, 'profit': 4500.25},
        {'rank': 7, 'username': 'BlackjackPro', 'wagered': 52300.00, 'profit': 6780.00},
        {'rank': 8, 'username': 'RouletteQueen', 'wagered': 47800.75, 'profit': -1200.50},
        {'rank': 9, 'username': 'PokerFace88', 'wagered': 43200.00, 'profit': 3450.00},
        {'rank': 10, 'username': 'BingoLover', 'wagered': 39500.25, 'profit': 2100.75}
    ]
    
    # Información del canal de Kick
    kick_channel_data = {
        'is_live': True,
        'title': '🎰 CASINO EN VIVO | WAGER RACE | !sorteo !puntos',
        'viewers': 2847,
        'thumbnail': None
    }
    
    # Clips destacados
    clips_data = [
        {
            'title': 'MEGA WIN $50,000 EN SLOTS 🤑',
            'thumbnail': 'https://via.placeholder.com/640x360/9333ea/ffffff?text=MEGA+WIN',
            'url': '#',
            'views': '125K'
        },
        {
            'title': 'Blackjack Perfect Hand 21 💎',
            'thumbnail': 'https://via.placeholder.com/640x360/ff6600/ffffff?text=BLACKJACK+21',
            'url': '#',
            'views': '98K'
        },
        {
            'title': 'Ruleta x100 INSANE 🔥',
            'thumbnail': 'https://via.placeholder.com/640x360/dc2626/ffffff?text=ROULETTE+X100',
            'url': '#',
            'views': '156K'
        }
    ]
    
    return render_template('demos/streamer_demo.html',
                         page=page_data,
                         usuario_json=usuario_json,
                         sorteos_activos=sorteos_activos,
                         ultimos_sorteos=ultimos_sorteos,
                         codigos_activos=codigos_activos,
                         points_config=points_config,
                         wager_race=wager_race_data,
                         wager_race_data=wager_race_data,
                         kick_channel=kick_channel_data,
                         clips=clips_data,
                         kick_user_authenticated=False,
                         viewer_points=0,
                         is_demo=True)
