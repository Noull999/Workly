#!/bin/bash
# Script de inicio para producción
# Lanza el bot de Kick en segundo plano y luego gunicorn

echo "Iniciando servicios de Workly..."

# Iniciar bot de Kick en segundo plano
echo "Iniciando bot de Kick..."
python3 kick_chat_bot.py &
BOT_PID=$!
echo "Bot iniciado con PID: $BOT_PID"

# Trap para limpiar procesos al salir
cleanup() {
    echo "Deteniendo servicios..."
    kill $BOT_PID 2>/dev/null
    exit 0
}
trap cleanup SIGTERM SIGINT

# Iniciar servidor web
echo "Iniciando servidor web..."
exec gunicorn --bind 0.0.0.0:5000 --reuse-port main:app
