# Banco de dados

Esta camada contém os scripts que definem a estrutura física do PostgreSQL.

## Migrations

- `001_create_usuarios.sql`: cria a tabela `usuarios` e o gatilho que atualiza `atualizado_em`.

O `docker-compose.yml` monta o script no diretório de inicialização da imagem PostgreSQL Chainguard. Ele é executado automaticamente somente quando o volume do banco está vazio.

Para aplicar manualmente em um banco já existente:

```bash
docker compose exec -T db psql -U poupescan -d poupescan -f /var/lib/postgres/initdb/poupescan-schema.sql
```
