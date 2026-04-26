# Workly

**Workly** es una plataforma web modular de gestión empresarial construida con Flask, pensada como un "todo en uno" para empresas chilenas que necesitan productividad, ventas, agendamiento y herramientas para creadores de contenido bajo un mismo techo.

Cada empresa activa solo los módulos que necesita y obtiene una experiencia personalizada con su marca, idioma (español 100%) y flujo de trabajo.

---

## ✨ Características principales

### 📦 Módulos activables por empresa
- **Inventario** — Catálogo de productos con sistema completo de categorías, control de stock y carga de imágenes.
- **Punto de Venta (POS)** — Caja registradora con manejo de turnos, múltiples métodos de pago, escáner de códigos de barras, modo offline con sincronización y reportes diarios.
- **Citas y Agendamiento** — Reserva pública de horas para servicios profesionales (peluquerías, clínicas, talleres, etc.).
- **Workspace tipo Notion** — Espacio colaborativo con editor enriquecido, archivos, jerarquía de páginas y colaboración en tiempo real.
- **Scrum / Agile** — Tableros kanban, backlog, sprints y seguimiento de proyectos.
- **Portfolio público** — Página corporativa con tu marca, servicios y contacto, accesible sin login cuando el módulo está activo.

### 💳 Pagos integrados
- **Mercado Pago multi-tenant** — Cada empresa conecta su propia cuenta de Mercado Pago vía OAuth. Soporta todos los métodos del mercado chileno.
- **Stripe** — Soporte para procesamiento internacional de tarjetas.

### 🎮 Herramientas para streamers (Kick.com)
- **Sistema de sorteos multi-streamer** — Los espectadores participan con sus puntos de fidelidad del canal.
- **Login con Kick OAuth** — Autenticación nativa con la cuenta de Kick.
- **Wager Race / Leaderboard** — Tabla mensual del Top 10 de jugadores de Stake.com con premios destacados.
- **Bot de chat de Kick** — Servicio Python que se conecta vía Pusher WebSockets para escuchar y responder en el chat en tiempo real.
- **Perfiles dinámicos de creador** — Páginas `/perfil/<email>` con diseño gaming, branding personalizable, clips destacados, redes sociales y modal de reclamo de premios.
- **Códigos canjeables** — Códigos promocionales que los espectadores canjean por puntos.

### 🎨 Diseño y experiencia
- Tema oscuro profesional con paleta personalizable por empresa (esquema base morado + naranja).
- Bootstrap 5, Font Awesome y Chart.js para visualizaciones.
- Animaciones suaves con GSAP, microinteracciones, skeleton screens y soporte a `prefers-reduced-motion`.
- Totalmente responsive (mobile, tablet, desktop).

### 🔐 Control de acceso
- Sistema multi-tenant por empresa.
- Roles granulares (super admin, admin de empresa, empleado, cliente público).
- Módulo **Demos** exclusivo para super admin con datos de muestra para presentaciones, sin afectar producción.

### 📊 Dashboard y analítica
- Tendencias de ventas, alertas de bajo stock, distribución de tareas.
- Reportes automáticos del POS al cierre de caja.

---

## 🛠️ Stack técnico

| Capa | Tecnología |
|------|-----------|
| Backend | Flask + Flask-Login + Flask-WTF + Flask-Migrate |
| ORM | SQLAlchemy |
| Base de datos | PostgreSQL (producción) / SQLite (desarrollo) |
| Frontend | Jinja2 + Bootstrap 5 + Font Awesome 6 + Chart.js + GSAP |
| Pagos | Mercado Pago SDK + Stripe |
| Streaming | Kick.com API + Pusher WebSockets (`pysher`) |
| Servidor | Gunicorn detrás de ProxyFix |
| Despliegue | Replit Deployments |

---

## 🚀 Puesta en marcha

### Requisitos
- Python 3.11+
- PostgreSQL (o SQLite para desarrollo local)
- `uv` o `pip` para gestionar dependencias

### Instalación

```bash
# Clonar el repositorio
git clone https://github.com/Noull999/Workly.git
cd Workly

# Instalar dependencias
uv sync   # o: pip install -e .
```

### Variables de entorno

Configurar las siguientes variables (en `.env` local o en los Secrets de Replit):

| Variable | Descripción |
|----------|-------------|
| `DATABASE_URL` | Cadena de conexión a PostgreSQL |
| `SESSION_SECRET` | Clave secreta de sesión Flask |
| `MP_CLIENT_ID` / `MP_CLIENT_SECRET` / `MP_ACCESS_TOKEN` / `MP_PUBLIC_KEY` | Credenciales de Mercado Pago |
| `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` | Credenciales de Stripe |
| `KICK_CLIENT_ID` / `KICK_CLIENT_SECRET` / `KICK_REDIRECT_URI` | OAuth de Kick.com |
| `KICK_BOT_CLIENT_ID` / `KICK_BOT_CLIENT_SECRET` | Credenciales del bot de chat |

### Ejecutar

```bash
gunicorn --bind 0.0.0.0:5000 --reuse-port --reload main:app
```

La aplicación queda escuchando en `http://localhost:5000`.

---

## 📂 Estructura del proyecto

```
.
├── app.py                  # Configuración de Flask + SQLAlchemy
├── main.py                 # Punto de entrada para gunicorn
├── models.py               # Modelos de base de datos
├── forms.py                # Formularios WTForms
├── kick_chat_bot.py        # Servicio del bot de chat de Kick
├── blueprints/             # Blueprints por módulo (POS, inventario, kick_bot, public, demos…)
├── templates/              # Plantillas Jinja2
├── static/                 # Assets estáticos (CSS, JS, imágenes)
├── helpers/ utils.py       # Utilidades compartidas
├── services/               # Servicios externos (Mercado Pago, Kick API…)
├── migrations/             # Migraciones de Alembic
└── data/                   # Datos JSON (configuración de streamers, etc.)
```

---

## 🌎 Casos de uso

- **PyMEs chilenas** que necesitan POS + inventario + agenda en una sola plataforma con Mercado Pago integrado.
- **Profesionales independientes** (peluqueros, kinesiólogos, talleres mecánicos) que quieren agenda pública y portfolio sin pagar plataformas separadas.
- **Equipos remotos** que necesitan un workspace colaborativo estilo Notion + tableros Scrum.
- **Streamers de Kick.com** que quieren un sitio profesional con sorteos automáticos, leaderboard de Stake, perfil personalizado y bot de chat — todo bajo su propia marca.

---

## 📄 Licencia

Proyecto privado de YANGLEE / Noull999. Todos los derechos reservados.

---

## 🤝 Contacto

- **Streamer / Creador**: [YANGLEE en Kick](https://kick.com/yanglee)
- **Issues / sugerencias**: [github.com/Noull999/Workly/issues](https://github.com/Noull999/Workly/issues)
