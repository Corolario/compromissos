# Usar imagem oficial do Python
FROM python:3.13-slim

# Definir diretório de trabalho
WORKDIR /app

# Copiar arquivos de dependências
COPY requirements.txt .

# Instalar dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY . .

# Criar diretório para banco de dados com permissões abertas
# As permissões serão gerenciadas pelo docker-compose.yml via user: UID:GID
RUN mkdir -p /app/data

# Expor porta
EXPOSE 5000

# Comando para iniciar a aplicação
#
# São 2 workers por padrão, não 4. O banco é SQLite, que aceita um escritor por
# vez, então mais processos aumentam a disputa por escrita sem ganho real para
# o volume de uma equipe pequena. Dois ainda evitam que um login demorado
# (o Argon2 leva cerca de 100 ms) segure as demais requisições.
# Ajuste com GUNICORN_WORKERS se o uso crescer.
CMD python init_db.py && gunicorn --bind 0.0.0.0:5000 --workers ${GUNICORN_WORKERS:-2} --timeout 120 app:app
