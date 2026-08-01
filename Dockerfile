# Usar imagem oficial do Python
FROM python:3.13-slim

# Fuso horário do contêiner
#
# A aplicação grava e exibe os horários no fuso do sistema, então este valor
# determina o que aparece na tela. A imagem slim não traz a base de fusos: sem
# instalar o tzdata, definir TZ não produz efeito algum e tudo continua em UTC,
# silenciosamente. Ajuste com a variável TZ no .env.
ENV TZ=America/Sao_Paulo
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

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
