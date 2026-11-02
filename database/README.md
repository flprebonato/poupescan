# Banco de dados

Esta camada contém os scripts que definem a estrutura física do PostgreSQL.

## Migrations

- `001_create_usuarios.sql`: cria a tabela `usuarios` e o gatilho que atualiza `atualizado_em`.

O `docker-compose.yml` monta o script no diretório de inicialização da imagem PostgreSQL Chainguard. Ele é executado automaticamente somente quando o volume do banco está vazio.

Para aplicar manualmente em um banco já existente:

```bash
docker compose exec -T db psql -U poupescan -d poupescan -f /var/lib/postgres/initdb/001_create_usuarios.sql
```

- `002_create_despesas.sql`: cria estabelecimentos por usuário, produtos, vínculos de códigos locais, despesas e itens. Inclui chaves estrangeiras, valores não negativos, quantidade positiva, imagem de até 10 MB e unicidade da chave de acesso por usuário. A exclusão da despesa remove os itens por `ON DELETE CASCADE`; a imagem está na própria linha da despesa.

Para um banco existente, aplique a migration de despesas sem recriar o volume:

```bash
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U poupescan -d poupescan < database/migrations/002_create_despesas.sql
```

- `003_add_atualizado_em_despesas.sql`: adiciona `atualizado_em` às despesas e o gatilho que registra a data de cada correção.

O Compose monta a pasta inteira em `/var/lib/postgres/initdb`; em um volume novo, os scripts são executados em ordem numérica. Em volumes existentes, o comando acima é necessário. Campos opcionais aceitam `NULL`, inclusive a hora (`hora_despesa`), descontos e valores não identificados. `descricao_original` preserva a leitura e `descricao` contém a correção confirmada pelo usuário.

O GTIN foi retirado do fluxo da aplicação. A coluna legada criada pela migration `002` pode permanecer no banco, sem uso pelo código atual; não é necessário apagar dados ou recriar volumes.
