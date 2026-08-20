#!/bin/bash
set -u
cd "$(dirname "$0")"
BIN="$PWD/DJEN Monitor"
if [ ! -x "$BIN" ]; then
  chmod +x "$BIN" 2>/dev/null || true
fi
"$BIN"
STATUS=$?
printf '\n'
if [ $STATUS -ne 0 ]; then
  echo "O DJEN Monitor terminou com erro (código $STATUS)."
  echo "Consulte os logs em: ~/Library/Application Support/DJEN Monitor/logs"
  read -r -p "Pressione ENTER para fechar."
fi
exit $STATUS
