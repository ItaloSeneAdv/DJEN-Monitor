from datetime import timedelta
import sys

from djen_monitor.api import DJENClient
from djen_monitor.time_utils import brasilia_today


def main():
    if len(sys.argv) != 3:
        print("Uso: python tools/live_smoke.py NUMERO UF")
        return 2
    numero, uf = sys.argv[1], sys.argv[2]
    today = brasilia_today()
    result = DJENClient(min_interval=0).query_oab(numero, uf, today - timedelta(days=2), today, include_variants=False)
    print(f"Itens: {len(result.items)} | completo: {result.complete} | requisicoes: {result.requests_made}")
    for item in result.items[:3]:
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
