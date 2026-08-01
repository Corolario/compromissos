#!/usr/bin/env python3
"""
Script para inicializar o banco de dados
Execute: python init_db.py
"""

import sys
from app import app, criar_tabelas

def init_database():
    """
    Invólucro de linha de comando para criar as tabelas.

    A criação em si fica em app.criar_tabelas, para não haver duas
    implementações da mesma coisa. Aqui só se acrescenta a mensagem de
    resultado e o código de saída, úteis no CMD do Dockerfile.
    """
    try:
        criar_tabelas()
        print("✓ Banco de dados inicializado com sucesso!")
        print(f"✓ Arquivo: {app.config['SQLALCHEMY_DATABASE_URI']}")
    except Exception as e:
        print(f"✗ Erro ao inicializar banco de dados: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    init_database()
