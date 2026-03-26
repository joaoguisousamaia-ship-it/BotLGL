# BotLGL

Bot Discord em Python com comandos:
- `/publicartiket`
- `/configurarrevisor`
- `/logs`
- `!addcargo`
- `!remcargo`

## Requisitos
- Python 3.11+
- Conta de bot no Discord Developer Portal

## Rodar localmente
1. Instale dependencias:
```bash
pip install -r requirements.txt
```

2. Crie seu arquivo `.env`:
```bash
cp .env.example .env
```

3. Edite `.env` e coloque o token:
```env
DISCORD_TOKEN=seu_token_aqui
```

4. Execute:
```bash
python bot.py
```

## Comandos
### Slash commands
- `/publicartiket canal:#canal categoria:(opcional)`
	- Publica painel com botao para abrir ticket.
	- Salva categoria opcional para criar os canais de ticket.
- `/configurarrevisor cargo:@Cargo`
	- Define o cargo que enxerga os tickets.
- `/logs canal:#canal`
	- Define o canal de logs.

### Prefix commands
- `!addcargo @membro @cargo`
	- Adiciona cargo em um membro (precisa `Gerenciar Cargos`).
- `!remcargo @membro @cargo`
	- Remove cargo de um membro (precisa `Gerenciar Cargos`).

## Deploy no Railway (passo a passo)
1. Suba o codigo para um repositorio GitHub.

2. Acesse Railway e crie um projeto novo:
	 - `New Project` -> `Deploy from GitHub Repo`.
	 - Selecione este repositorio.

3. No projeto do Railway, abra a aba de variaveis (`Variables`) e adicione:
	 - `DISCORD_TOKEN` = token do seu bot.

4. O arquivo `Procfile` ja esta configurado com:
```txt
worker: python bot.py
```

5. O projeto inclui `nixpacks.toml` para forcar o build Python no Railway.
	- Isso evita erro como: `Script start.sh not found`.

6. Após deploy, veja os logs para confirmar que apareceu:
	 - `Bot online como ...`
	 - `Slash commands sincronizados: ...`

7. Convide o bot para seu servidor com os escopos:
	 - `bot`
	 - `applications.commands`

8. Permissoes recomendadas no convite:
	 - `Manage Roles`
	 - `Manage Channels`
	 - `Send Messages`
	 - `Read Message History`

## Observacoes
- As configuracoes por servidor ficam em `config.json`.
- Em ambiente Railway, o sistema de arquivos pode ser efemero. Se precisar persistencia forte, o ideal e migrar para banco (ex: PostgreSQL/Redis).
