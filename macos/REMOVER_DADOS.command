#!/bin/bash
set -u
LABEL="br.italosene.djenmonitor"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DATA="$HOME/Library/Application Support/DJEN Monitor"
REPORTS="$HOME/Documents/DJEN Monitor"

launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
rm -f "$PLIST"
rm -rf "$DATA"

echo "Configuração, histórico, logs e agendamento removidos."
printf "Apagar também as planilhas em '%s'? [s/N]: " "$REPORTS"
read -r ANSWER
case "$ANSWER" in
  s|S|sim|SIM|Sim) rm -rf "$REPORTS"; echo "Planilhas removidas." ;;
  *) echo "Planilhas preservadas." ;;
esac
read -r -p "Pressione ENTER para fechar."
