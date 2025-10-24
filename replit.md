# Workly

## Overview

Workly is a web-based, modular enterprise management system built with Flask, designed as a comprehensive productivity platform. It integrates inventory management, point-of-sale (POS), appointment scheduling, a Notion-style collaborative workspace, agile project management (Scrum), and presentation pages. The system supports multi-company operations with activatable modules, advanced role control, real-time collaboration, and full customization per enterprise. Its ambition is to be an all-in-one solution for businesses seeking modular, scalable, and integrated management tools, including market-specific payment integrations like Mercado Pago for Chile, and streamer tools like Kick.com integration.

## User Preferences

- Preferred communication style: Simple, everyday language
- Application must be fully localized in Spanish for Chilean company use
- Remove price/value fields from all models, forms, and templates as they are not needed
- Complete category system for organizing inventory items
- Application name changed to "Workly" throughout the system
- Business model: Enterprise productivity platform with modular activation
- Professional access control: Multi-tenant system with comprehensive role management
- Modular system: 6 core modules - Inventory, POS, Appointments, Notion Workspace, Scrum Agile, and Portfolio
- Advanced features: Real-time collaboration, rich text editing, file management, kanban boards, project tracking
- Public pages: Company portfolio and booking system accessible without login when modules are active
- Color scheme: Purple background with orange text for modern, professional appearance

## System Architecture

The Workly platform is built with Flask, utilizing Flask-SQLAlchemy for ORM, Flask-Login for authentication, and Flask-WTF for form handling. It supports a multi-tenant architecture where each company can activate specific modules.

### Core Framework & UI/UX
- **Web Framework**: Flask for a lightweight and flexible backend.
- **Database**: SQLAlchemy ORM for data abstraction, primarily using PostgreSQL, with SQLite for development.
- **Authentication**: Flask-Login for session management and Werkzeug for secure password handling.
- **Frontend**: Jinja2 templating, Bootstrap 5 (dark theme), Font Awesome for icons, and vanilla JavaScript for interactivity. Color scheme uses purple backgrounds and orange text.

### Modular System Design
- **Company-based modules**: Businesses activate modules based on their needs.
- **Core Modules**: Inventory, POS, Appointments, Notion-style Workspace, Scrum Agile, and Portfolio.
- **Dynamic Navigation**: UI adjusts to show only active modules.
- **Public Pages**: Portfolio and booking pages are publicly accessible when activated.
- **Dynamic User Profiles**: JSON-driven `/perfil/<email>` pages for creators/streamers, featuring modern gaming design, customizable branding, and integration for featured clips and contact options.

### Key Feature Implementations
- **Advanced POS**: Cash management, multiple payment methods, barcode scanning, offline mode with sync, and daily reporting.
- **Dashboard Analytics**: Integration with Chart.js for visualizing sales trends, low stock alerts, and task distribution, using dynamic backend data.
- **Mercado Pago Integration**: Multi-tenant OAuth for connecting company-specific Mercado Pago accounts. Supports secure OAuth flow, token management, and various payment methods for the Chilean market.
- **Kick Integration System**: Multi-streamer raffle system allowing viewers to use Kick loyalty points. Features OAuth login, multi-streamer support via JSON config, public raffle pages, streamer admin panel, and real-time Kick API integration for channel stats and point verification.

## External Dependencies

- **Web Framework**: Flask
- **ORM**: Flask-SQLAlchemy
- **Authentication**: Flask-Login, Werkzeug
- **Forms**: Flask-WTF, WTForms
- **Database Migrations**: Flask-Migrate (for PostgreSQL)
- **Frontend Libraries**: Bootstrap 5 (via CDN), Font Awesome 6 (via CDN), Chart.js
- **Payment Gateway**: Mercado Pago API (via `mercadopago` Python SDK)
- **Streaming Platform API**: Kick.com API (for loyalty points, channel stats)
- **Deployment**: ProxyFix for proxy header handling
```