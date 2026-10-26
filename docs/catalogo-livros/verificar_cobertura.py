"""
Confere se os catalogos cobrem todas as paginas de um livro.

    python docs/catalogo-livros/verificar_cobertura.py nrc 406
    python docs/catalogo-livros/verificar_cobertura.py nasem 562

Cada catalogo deve ter, na secao "1. Cobertura", uma linha `PDF N | livro p. M | assunto` por pagina.
"""

import re
import sys
from pathlib import Path

livro, total = sys.argv[1], int(sys.argv[2])
pasta = Path(__file__).parent / livro
linha = re.compile(r"^\s*(?:[-*]\s*)?`?PDF\s+(\d+)\s*\|", re.MULTILINE)

paginas: dict[int, str] = {}
duplicadas: list[tuple[int, str, str]] = []
for arquivo in sorted(pasta.glob("*.md")):
    for numero in map(int, linha.findall(arquivo.read_text(encoding="utf-8"))):
        if numero in paginas:
            duplicadas.append((numero, paginas[numero], arquivo.name))
        paginas[numero] = arquivo.name

faltando = [n for n in range(1, total + 1) if n not in paginas]
fora = sorted(n for n in paginas if not 1 <= n <= total)
print(f"{livro}: {len(paginas)} de {total} paginas com linha de cobertura, em {len(set(paginas.values()))} catalogos")
print("faltando:", faltando or "nenhuma")
if fora:
    print("fora do intervalo:", fora)
if duplicadas:
    print("duplicadas:", duplicadas[:10])
sys.exit(1 if faltando or fora else 0)
