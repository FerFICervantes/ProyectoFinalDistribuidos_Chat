#!/bin/bash
# Script de inicio para Azure App Service

echo "Iniciando servidor ChatLamport..."

# Instalar dependencias si es necesario
pip install -r requirements.txt

# Crear directorio para base de datos
mkdir -p /home/site/wwwroot/database

# Iniciar la aplicación
python app.py