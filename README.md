# BotLGL

Bot Discord em Python para tickets, questionnaires, revisao de transcript e gerenciamento de cargos.

## Requisitos
- Python 3.11+
- Bot criado no Discord Developer Portal
- Intents de `Message Content` e `Server Members` habilitadas no bot

## Rodar localmente
1. Instale as dependencias:
```bash
pip install -r requirements.txt
```

2. Crie o arquivo `.env`:
```bash
cp .env.example .env
```

3. Defina o token do bot:
```env
DISCORD_TOKEN=seu_token_aqui
```

4. Execute:
```bash
python bot.py
```

## Comandos
### Slash commands administrativos
- `/configurar_canal canal:#canal`
  Define o canal de envio dos transcripts para revisao.
- `/configurar_revisor cargo:@cargo`
  Define o cargo que pode ver tickets e aceitar ou rejeitar transcripts.
- `/configurar_staff cargo:@cargo`
  Define o cargo staff autorizado a usar `!addcargo` e `!remcargo`.
- `/configurar_logs_sets canal:#canal`
  Define o canal de transcripts. Mantido para compatibilidade com o fluxo antigo.
- `/logs canal:#canal`
  Define o canal de logs de comandos e acoes.
- `/publicar_ticket`
  Publica o painel de ticket no canal atual.
- `/enviar_botao_ticket canal:#canal`
  Publica o painel de ticket no canal informado.

### Slash commands de uso
- `/set`
  Cria um canal de ticket privado e inicia as perguntas.
- `/questoes`
  Faz as mesmas perguntas no canal atual.

### Prefix commands
- `!addcargo @membro @cargo`
  Adiciona um cargo. Exige `Manage Roles` e, se configurado, o cargo staff.
- `!remcargo @membro @cargo`
  Remove um cargo. Exige `Manage Roles` e, se configurado, o cargo staff.

## Fluxo recomendado
1. Use `/configurar_revisor` para definir quem revisa transcripts.
2. Use `/configurar_canal` ou `/configurar_logs_sets` para definir onde os transcripts chegam.
3. Use `/logs` para definir o canal de auditoria.
4. Use `/publicar_ticket` ou `/enviar_botao_ticket` para publicar o painel.

## Deploy no Railway
1. Suba o codigo para um repositorio GitHub.
2. No Railway, crie um projeto com `Deploy from GitHub Repo`.
3. Adicione a variavel `DISCORD_TOKEN`.
4. O projeto ja contem `Procfile` e `nixpacks.toml` apontando para `python bot.py`.
5. Confira os logs ate aparecerem mensagens como `Bot online como ...` e `Slash commands sincronizados: ...`.

## Observacoes
- As configuracoes sao salvas por servidor em `config.json`.
- Os transcripts aceitos sao gravados em arquivos JSON locais. Em hosts com filesystem efemero, isso nao serve como persistencia de longo prazo.
- Se precisar persistencia real para transcripts e configuracoes, o proximo passo ideal e migrar para banco de dados.
