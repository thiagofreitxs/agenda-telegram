# 📅 Agenda pessoal no Telegram + Google Calendar

Um bot de Telegram **só seu** que:

- 📝 cria eventos no seu **Google Calendar** conversando com ele;
- 📅 mostra a agenda de **hoje**, **amanhã**, **próximos 7 dias** e **próximos compromissos**;
- ⏰ te manda uma **mensagem no Telegram antes de cada compromisso**;
- 🔒 só responde aos IDs do Telegram que você autorizar.

---

## Como funciona

```
Você (Telegram)  ──►  Bot (Python)  ──►  Google Calendar API
                          │
                          └── job a cada 60s: procura eventos próximos e avisa
```

O bot roda em **polling** (não precisa de domínio nem HTTPS), então funciona bem
em VPS, Railway, Render, Fly.io, etc.

> ⚡ **Jeito rápido:** depois de instalar as dependências, rode o assistente que faz
> quase tudo por você (valida o token, descobre seu ID e autoriza o Google):
>
> ```bash
> .venv\Scripts\python.exe configurar.py      # Windows
> # .venv/bin/python configurar.py            # Linux/macOS
> ```
>
> Ele só precisa que você crie o bot no @BotFather e faça login no Google uma vez —
> essas duas coisas dependem da sua conta e não têm como ser automatizadas.
> Depois é só rodar `run.bat` (Windows) ou `python -m app.main`.

Comandos disponíveis:

| Comando | O que faz |
|---|---|
| `/novo Dentista amanhã às 14h` | Cria o evento |
| *(só escrever)* `Reunião com João sexta 10:30` | Também cria o evento |
| `/hoje` · `/amanha` · `/semana` | Consulta a agenda |
| `/proximos 10` | Próximos compromissos |
| `/cancelar` | Lista e cancela um evento |
| `/lembrete 60` | Avisar 60 min antes |
| `/diario 08:00` | Horário do aviso de eventos de "dia inteiro" |
| `/status` · `/id` · `/ajuda` | Configuração e informações |

---

## Passo a passo

### 1. Crie o bot no Telegram

1. Fale com [@BotFather](https://t.me/BotFather) → `/newbot`.
2. Guarde o **token** (formato `123456:AAA...`).

### 2. Crie as credenciais do Google (uma vez)

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/) e crie um projeto.
2. **APIs e Serviços → Biblioteca** → ative a **Google Calendar API**.
3. **APIs e Serviços → Tela de consentimento OAuth**:
   - Tipo: **Externo**; adicione você mesmo como **usuário de teste**.
4. **APIs e Serviços → Credenciais → Criar credenciais → ID do cliente OAuth**:
   - Tipo: **App para computador (Desktop app)**.
   - Baixe o JSON e salve como `client_secret.json` na pasta do projeto.

> Alternativa sem OAuth: criar uma **conta de serviço**, baixar o JSON e
> **compartilhar seu calendário** com o e-mail da conta de serviço
> (permissão "Fazer alterações nos eventos"). Aí use `GOOGLE_SERVICE_ACCOUNT_FILE`
> e defina `GOOGLE_CALENDAR_ID` como o **e-mail do seu Google** (ex.:
> `seunome@gmail.com`), porque contas de serviço não têm um "primary".

### 3. Configure o projeto

```bash
# Clone/copie o projeto e crie um ambiente virtual
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt

# Crie o .env a partir do exemplo
copy .env.example .env      # Windows
# cp .env.example .env      # Linux/macOS
```

Edite o `.env` e preencha pelo menos:

```env
TELEGRAM_BOT_TOKEN=seu_token_do_botfather
ALLOWED_TELEGRAM_IDS=seu_id_numerico
TIMEZONE=America/Sao_Paulo
GOOGLE_CALENDAR_ID=primary
```

> Não sabe seu ID? Rode o bot (passo 5), envie `/id` e copie o número.
> Enquanto `ALLOWED_TELEGRAM_IDS` estiver vazio o bot avisará que falta configurar.

### 4. Autorize o acesso ao Google Calendar

```bash
python authorize_google.py
```

Vai abrir o navegador, você faz login e autoriza. Isso gera o `token.json`.
Esse token se renova sozinho — você só precisa fazer isso uma vez.

### 5. Rode o bot

```bash
python -m app.main
```

No Telegram, envie `/start` e depois teste:

```
/novo Reunião de teste amanhã às 15h
```

O evento aparece no seu Google Calendar e você recebe um aviso no horário. 🎉

### 6. Conferir se está tudo certo

```bash
.venv\Scripts\python.exe check_setup.py          # Windows
# .venv/bin/python check_setup.py                # Linux/macOS
```

Para testar a conexão real com o Google Calendar:

```bash
python check_setup.py --google
```

No Windows você também pode dar duplo clique em **`run.bat`** para iniciar o bot.

---

## Deploy na nuvem

Como o bot usa **polling**, você precisa de algo que rode 24h. Opções:

### Render (Background Worker) — recomendado pela simplicidade

1. Suba o projeto no GitHub.
2. Crie um **Background Worker** apontando para o repositório
   (ou use o `render.yaml` incluso).
3. Build: `pip install -r requirements.txt`
4. Start: `python -m app.main`
5. Adicione as variáveis de ambiente no painel — incluindo o
   **conteúdo** do `token.json` em `GOOGLE_TOKEN_JSON` (uma linha só).

### Docker (VPS, Docker Compose, etc.)

```bash
# Coloque .env e token.json na mesma pasta
docker compose up -d --build
```

O `docker-compose.yml` já monta um volume em `./data` para o SQLite e o token.

### Railway / Fly.io / VPS

Use o `Dockerfile` ou o `Procfile`. Garanta as variáveis de ambiente e um volume
para persistir `data/` (banco de lembretes).

> 💡 Para pegar o conteúdo do token em uma linha (PowerShell):
> `(Get-Content token.json -Raw) -replace "`n","" -replace "`r",""`

---

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | Token do @BotFather (**obrigatório**) |
| `ALLOWED_TELEGRAM_IDS` | — | IDs autorizados, separados por vírgula (**obrigatório**) |
| `TIMEZONE` | `America/Sao_Paulo` | Fuso usado para interpretar e exibir horários |
| `GOOGLE_CALENDAR_ID` | `primary` | Calendário alvo |
| `GOOGLE_TOKEN_FILE` / `GOOGLE_TOKEN_JSON` | `token.json` | Credencial OAuth |
| `GOOGLE_CLIENT_SECRET_FILE` | `client_secret.json` | Usado só para gerar o token |
| `GOOGLE_SERVICE_ACCOUNT_FILE` / `_JSON` | — | Alternativa à OAuth |
| `DEFAULT_EVENT_DURATION_MIN` | `60` | Duração padrão |
| `DEFAULT_EVENT_TIME` | `09:00` | Hora usada quando você só informa a data |
| `REMINDER_LEAD_MINUTES` | `30` | Antecedência do aviso |
| `REMINDER_CHECK_INTERVAL_SECONDS` | `60` | Intervalo de verificação |
| `ALL_DAY_REMINDER_TIME` | `08:00` | Aviso de eventos de dia inteiro |
| `DATABASE_PATH` | `data/agenda.db` | Banco SQLite de controle |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## Estrutura do projeto

```
.
├── app/
│   ├── config.py                 # leitura/validação do .env
│   ├── db.py                     # SQLite: lembretes já enviados + ajustes
│   ├── handlers.py               # comandos e mensagens do Telegram
│   ├── main.py                   # ponto de entrada (python -m app.main)
│   ├── services/
│   │   ├── calendar_service.py   # Google Calendar (OAuth e service account)
│   │   └── reminder_service.py   # verificação periódica + envio de avisos
│   └── utils/
│       └── parsing.py            # datas em linguagem natural (pt-BR)
├── tests/test_parsing.py
├── authorize_google.py           # gera o token.json (rode uma vez)
├── configurar.py                 # assistente guiado de configuração
├── check_setup.py                # verifica se está tudo pronto
├── run.bat                       # atalho para iniciar no Windows
├── Dockerfile · docker-compose.yml · Procfile · render.yaml
├── requirements.txt
└── .env.example
```

---

## Perguntas frequentes

**O bot avisa se eu criar o evento direto no Google Calendar?**
Sim. O aviso é baseado na sua agenda, então qualquer evento (criado por aqui ou
pelo celular) é detectado.

**E se o servidor reiniciar?**
Os lembretes já enviados ficam no SQLite, então você não recebe mensagens
duplicadas. (Mantenha o volume `data/` persistente.)

**Dá para mais de uma pessoa usar?**
O projeto é pensado para uso pessoal (uma agenda). Para compartilhar, adicione
outros IDs em `ALLOWED_TELEGRAM_IDS` — todos verão/editarão o mesmo calendário.

**Quero criar eventos com participantes/convites.**
Hoje o foco é a sua própria agenda. Isso pode ser estendido no
`calendar_service.create_event` adicionando o campo `attendees`.

---

## Licença

Uso pessoal. Sinta-se livre para adaptar.
