#!/bin/sh
# Monta o visualizador (web/viewer.html) em dois lugares:
#   web/aranha.html                  -> para abrir direto no navegador
#   app/src/main/assets/index.html   -> a tela do app Android
cd "$(dirname "$0")"
mkdir -p app/src/main/assets
{ printf '<!doctype html>\n<html lang="pt-BR"><head><meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'; cat web/viewer.html; printf '\n</html>\n'; } > web/aranha.html
cp web/aranha.html app/src/main/assets/index.html
echo "visualizador montado"
