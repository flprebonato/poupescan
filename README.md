# Sobre

O **PoupeScan** é um sistema desenvolvido para centralizar e organizar o histórico de despesas do usuário. Por meio do envio de imagens de comprovantes de compras, a **inteligência artificial** analisa e extrai automaticamente as informações relevantes, utilizando esses dados para alimentar o banco de dados.

# Significado

O nome **PoupeScan** representa justamente a proposta da solução:

- **Poupe**: está relacionado à economia proporcionada pela análise do histórico de compras.
- **Scan**: faz referência à digitalização e leitura dos comprovantes.

A ideia é transformar informações que antes ficavam apenas registradas em notas e recibos em **dados úteis**, capazes de auxiliar o usuário na tomada de decisões de compra.

# Objetivo

O PoupeScan facilita a consulta e a análise do histórico de compras, permitindo:

- acompanhar a evolução dos gastos;
- comparar preços ao longo do tempo;
- consultar produtos adquiridos;
- analisar quantidades compradas;
- identificar variações de preço;
- encontrar oportunidades de economia.

Dessa forma, o usuário consegue utilizar seu próprio histórico de consumo para tomar decisões.

# Estrutura

Cadastro, login e organização de despesas com FastAPI, PostgreSQL, Ollama e uma interface responsiva em HTML, CSS e JavaScript.

```text
poupescan/
├── backend/
│   ├── app/              # API, banco, segurança e leitura por IA
│   │   ├── api/          # Dependências de autenticação e organização das rotas
│   │   │   └── routes/   # Rotas de usuários, despesas, páginas e saúde da aplicação
│   │   ├── core/         # Configurações, hash de senhas, tokens JWT e CAPTCHA
│   │   ├── database/     # Modelos SQLAlchemy, conexão e sessões do banco
│   │   ├── schemas/      # Esquemas Pydantic para validação e respostas da API
│   │   ├── services/     # Leitura por IA, prompts, consulta de CNPJ, QR codes e cálculos dos comprovantes
│   │   └── main.py       # Inicialização do FastAPI, registro das rotas, CORS e arquivos estáticos
│   ├── tests/            # Testes do backend
│   │   └── fixtures/     # Imagem do comprovante usado no teste de leitura
│   ├── Dockerfile        # Imagem Python do backend
│   └── requirements.txt  # Dependências Python
├── frontend/
│   ├── index.html        # Login e cadastro
│   ├── central.html      # Área autenticada e despesas
│   ├── css/              # Estilos
│   └── js/               # JavaScript do navegador
├── database/
│   ├── migrations/       # Scripts SQL versionados
│   └── README.md         # Instruções do banco
├── scripts/              # Preparação do ambiente e do modelo de IA
├── deploy.sh             # Inicialização com seleção de hardware
└── docker-compose.yml    # Aplicação, PostgreSQL e Ollama
```

## Como o projeto funciona

- O usuário cria uma conta com CAPTCHA matemático e faz login.
- O FastAPI valida os dados e armazena a senha como hash no PostgreSQL.
- Depois do login, a sessão fica em um cookie protegido e o usuário é enviado para `/app`.
- Em **Nova despesa**, o usuário envia um comprovante JPG ou PNG de até 10 MB.
- A IA extrai os dados e os itens da compra para revisão antes de salvar.
- O CNPJ é consultado para preencher o nome e o endereço do estabelecimento; a confirmação é necessária para salvar.
- Em **Minhas despesas**, o usuário consulta, corrige e exclui suas compras registradas. A correção usa a mesma tela de conferência e mantém a imagem original.

Os prompts da IA ficam em [`backend/app/services/reader.py`](backend/app/services/reader.py), na variável `PROMPT` e nas constantes `PROMPT_*` usadas para ler partes do comprovante. O modelo padrão é o **Qwen3-VL 4B** (`qwen3-vl:4b-instruct-q4_K_M`), configurado por `OLLAMA_MODEL` no `.env`.

## Executar com Docker

Requisitos: Docker com Docker Compose, Bash e Python 3.10 ou superior no host.

1. Copie `.env.example` para `.env` e troque `POSTGRES_PASSWORD` e `AUTH_SECRET_KEY`:

   ```bash
   cp .env.example .env
   ```

2. Inicie os containers e prepare o modelo de IA:

   ```bash
   ./deploy.sh
   ```

3. Acesse [http://localhost:8000](http://localhost:8000).

O Compose parte de uma configuração de CPU. O script baixa o modelo quando necessário, testa o hardware disponível e atualiza o Compose com a configuração aprovada. Para usar somente CPU, execute `./deploy.sh --cpu`. GPUs NVIDIA exigem driver e NVIDIA Container Toolkit; Intel/AMD exigem Docker Engine local no Linux, drivers Vulkan e `vulkaninfo`.

A documentação interativa da API fica em [http://localhost:8000/docs](http://localhost:8000/docs).

A aplicação usa a imagem oficial `python:3.12-slim-bookworm`, o banco usa PostgreSQL da Chainguard e a IA usa `ollama/ollama`. Os volumes `postgres_data` e `ollama_models` preservam o banco e os modelos entre reinicializações.

Em um banco vazio, as migrations são executadas automaticamente. Se o banco já existia antes da funcionalidade de despesas, aplique:

```bash
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U poupescan -d poupescan < database/migrations/002_create_despesas.sql
```

### Usar com Live Server

Também é possível abrir `frontend/index.html` com o Live Server do VS Code. Mantenha os containers rodando: o frontend da porta `5500` usa a API em `http://127.0.0.1:8000`.

## Endpoints

- `POST /api/auth/cadastro` — cria a conta e inicia a sessão.
- `GET /api/auth/captcha` — gera a pergunta e o token do CAPTCHA.
- `POST /api/auth/login` — autentica e inicia a sessão.
- `GET /api/auth/me` — retorna o usuário autenticado.
- `PATCH /api/auth/me` — atualiza nome, e-mail e senha após confirmar a senha atual.
- `POST /api/auth/logout` — encerra a sessão.
- `POST /api/scan` — lê o comprovante sem salvar a despesa.
- `GET /api/estabelecimentos/cnpj/{cnpj}` — consulta os dados do estabelecimento.
- `POST /api/despesas` — salva o comprovante e os dados revisados.
- `GET /api/despesas` — lista as despesas do usuário.
- `GET /api/despesas/{id}` — retorna os detalhes de uma despesa.
- `PUT /api/despesas/{id}` — corrige os dados e a lista completa de itens, mantendo a imagem original.
- `GET /api/despesas/{id}/imagem` — retorna a imagem original.
- `DELETE /api/despesas/{id}` — exclui a despesa.
- `GET /api/health` — verifica aplicação e banco.

A autenticação usa JWT em cookie `HttpOnly` com `SameSite=Lax`. Em produção, use HTTPS e configure `COOKIE_SECURE=true`.

## Desenvolvimento local

Use Python 3.12, a mesma versão da imagem Docker. Configure no `.env` a variável `DATABASE_URL` para um PostgreSQL acessível com as migrations aplicadas e `OLLAMA_URL` para um Ollama com o modelo configurado em `OLLAMA_MODEL` disponível. Para Ollama no próprio computador, use `http://localhost:11434`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
uvicorn backend.app.main:app --reload
```

Para executar os testes, em outro terminal com o ambiente virtual ativado:

```bash
pytest backend/tests
```

### Teste de leitura do comprovante via CLI

O teste [`test_comprovante_real.py`](backend/tests/test_comprovante_real.py) usa apenas [`comprovante_teste.jpeg`](backend/tests/fixtures/comprovante_teste.jpeg) como arquivo de entrada. Ele chama `analisar_comprovante`, a mesma função usada por `POST /api/scan`, com os prompts `PROMPT` e `PROMPT_*` de [`reader.py`](backend/app/services/reader.py). Não usa transcrição pronta nem respostas simuladas da IA.

Com o ambiente virtual ativado e o Ollama acessível em `OLLAMA_URL`, contendo o modelo configurado em `OLLAMA_MODEL`, execute na raiz do projeto:

```bash
POUPESCAN_TESTE_REAL=1 python -m pytest backend/tests/test_comprovante_real.py -v -s
```

O comando mostra o modelo e os dados retornados e verifica CNPJ, data, hora, chave de acesso, forma de pagamento, os 11 itens, quantidades, preços e descontos contra os valores esperados da imagem. Esses valores ficam nas verificações do teste e não são enviados ao modelo. O teste também executa a consulta de CNPJ configurada pela aplicação; não exige o servidor FastAPI nem o PostgreSQL em execução e não salva uma despesa.

A leitura pode levar alguns minutos, conforme o hardware e `OLLAMA_TIMEOUT`. Falhas de conexão ou diferenças nos dados fazem o teste falhar. Sem `POUPESCAN_TESTE_REAL=1`, esse teste fica marcado como ignorado (`skipped`) na suíte normal. Para verificar também o cadastro e a persistência, siga o teste manual abaixo.

### Teste leitura do comprovante via interface web

O arquivo [`backend/tests/fixtures/comprovante_teste.jpeg`](backend/tests/fixtures/comprovante_teste.jpeg) permite testar o envio, a leitura por IA, a revisão e o cadastro de uma despesa. Ele mantém os dados do estabelecimento, da compra e a chave de acesso. CPF, identificadores do cartão e QR code foram removidos.

Com o servidor local iniciado pelo comando `uvicorn` acima, o PostgreSQL e o Ollama disponíveis e o modelo configurado em `OLLAMA_MODEL` instalado:

1. Acesse [http://localhost:8000](http://localhost:8000) e entre em uma conta de teste.
2. Abra **Nova despesa**, selecione `backend/tests/fixtures/comprovante_teste.jpeg` e clique em **Enviar**.
3. Aguarde a leitura e a consulta de CNPJ. O envio usa `POST /api/scan` e os mesmos prompts da aplicação, definidos em `PROMPT` e `PROMPT_*` de [`backend/app/services/reader.py`](backend/app/services/reader.py). Não é necessário fornecer um prompt separado.
4. Na tela de conferência, os dados extraídos podem ser visualizados e editados se necessário.
5. Ao salvar, você pode conferir o registro em **Minhas despesas**. Abra o registro e confira os itens, totais e a imagem. Use **Editar despesa** para corrigir dados e itens já salvos. Recarregue a página para verificar a persistência e exclua a despesa de teste ao terminar.
