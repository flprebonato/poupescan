# Sobre

O **PoupeScan** é um sistema desenvolvido para centralizar e organizar o histórico de despesas do usuário. Por meio do envio de imagens de comprovantes de compras, a **inteligência artificial** analisa e extrai automaticamente as informações relevantes, utilizando esses dados para alimentar o banco de dados.

# Significado

O nome **PoupeScan** representa justamente a proposta da solução:

* **Poupe**: está relacionado à economia proporcionada pela análise do histórico de compras.
* **Scan**: faz referência à digitalização e leitura dos comprovantes.

A ideia é transformar informações que antes ficavam apenas registradas em notas e recibos em **dados úteis**, capazes de auxiliar o usuário na tomada de decisões de compra.

# Objetivo

O PoupeScan facilita a consulta e a análise do histórico de compras, permitindo:

* acompanhar a evolução dos gastos;
* comparar preços ao longo do tempo;
* consultar produtos adquiridos;
* analisar quantidades compradas;
* identificar variações de preço;
* encontrar oportunidades de economia.

Dessa forma, o usuário consegue utilizar seu próprio histórico de consumo para tomar decisões.

# Estrutura

Fluxo completo de cadastro e login com FastAPI, PostgreSQL e uma interface responsiva em HTML, CSS e JavaScript.

```text
poupescan/
├── backend/
│   ├── app/              # API, banco, modelos e segurança
│   ├── tests/            # Testes da autenticação
│   ├── Dockerfile        # Imagem Python do backend
│   └── requirements.txt  # Dependências Python
├── frontend/
│   ├── index.html        # Login e cadastro
│   ├── dashboard.html    # Área autenticada
│   ├── css/              # Estilos
│   └── js/               # JavaScript do navegador
├── database/
│   ├── migrations/       # Scripts SQL versionados
│   └── README.md         # Instruções do banco
└── compose.yaml          # Aplicação e PostgreSQL
```

## Como o projeto funciona

- O HTML possui um formulário de login e outro de cadastro.
- O JavaScript adiciona ou remove a classe CSS `show-register` para fazer a transição.
- Antes do cadastro, o backend gera um CAPTCHA matemático com validade de 5 minutos.
- Ao enviar um formulário, o JavaScript chama a API FastAPI.
- O FastAPI valida os dados, gera o hash da senha e salva o usuário no PostgreSQL.
- A pasta `database/migrations` contém a criação das tabelas e regras do banco.
- Depois do login, a sessão fica em um cookie protegido e o usuário é enviado para `/app`.

## Executar com Docker

1. Copie `.env.example` para `.env` e troque `POSTGRES_PASSWORD` e `AUTH_SECRET_KEY`.
2. Inicie os dois containers:

   ```bash
   docker compose up --build
   ```

3. Acesse [http://localhost:8000](http://localhost:8000).

A documentação interativa da API fica em [http://localhost:8000/docs](http://localhost:8000/docs).

### Usar com Live Server

Também é possível abrir `frontend/index.html` com o Live Server do VS Code. Nesse caso, mantenha os containers rodando, pois o frontend da porta `5500` continuará usando a API em `http://127.0.0.1:8000`.

O projeto usa somente imagens públicas gratuitas da Chainguard:

- `cgr.dev/chainguard/python:latest-dev` para instalar as dependências.
- `cgr.dev/chainguard/python:latest` para executar a aplicação.
- `cgr.dev/chainguard/postgres:latest` para o banco de dados.

O uso de duas etapas no Dockerfile evita colocar `pip` e ferramentas de desenvolvimento na imagem final.

## Endpoints

- `POST /api/auth/cadastro` — cria a conta e inicia a sessão.
- `GET /api/auth/captcha` — gera a pergunta e o token assinado do CAPTCHA.
- `POST /api/auth/login` — autentica e inicia a sessão.
- `GET /api/auth/me` — retorna o usuário autenticado.
- `POST /api/auth/logout` — encerra a sessão.
- `GET /api/health` — verifica aplicação e banco.

A autenticação usa um JWT em cookie `HttpOnly` com `SameSite=Lax`. Em produção, sirva a aplicação com HTTPS e configure `COOKIE_SECURE=true`.

## Desenvolvimento local

Use Python 3.12 ou superior e um PostgreSQL acessível pela variável `DATABASE_URL`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
uvicorn backend.app.main:app --reload
pytest backend/tests
```

Em um volume vazio, o PostgreSQL executa automaticamente as migrations da pasta `database/migrations`. O volume Docker `postgres_data` mantém os dados entre reinicializações.
