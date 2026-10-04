# ☁️ Colocando o bot na nuvem (24h no ar)

Objetivo: o bot te avisa **mesmo com o PC desligado**.

> 🔑 **Importante:** eu (assistente) não consigo criar a conta de hospedagem no
> seu nome — isso exige seu e-mail/GitHub. Mas está tudo preparado: você só vai
> clicar. Use o arquivo **`deploy_env.txt`** (na pasta do projeto) para copiar os
> valores.

---

## Opção A — Render (mais fácil para começar)

### 1. Criar conta no GitHub e subir o projeto

1. Crie uma conta grátis em **https://github.com** (se ainda não tiver).
2. Crie um repositório **privado** chamado `agenda-telegram`.
3. Baixe o **GitHub Desktop** (https://desktop.github.com) — é o jeito mais fácil
   sem usar comandos:
   - Abra o GitHub Desktop → *File → Add local repository*
   - Escolha a pasta do projeto (`C:\Users\Administrator\Documents\Projeto Padrão`)
   - Clique em **Publish repository** e marque **Keep this code private**

### 2. Criar o serviço no Render

1. Crie conta em **https://render.com** (pode entrar com o GitHub).
2. Clique em **New → Web Service** (ou **Background Worker**, se preferir).
3. Conecte o repositório `agenda-telegram`.
4. Configurações:
   - **Runtime**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python -m app.main`
   - **Instance Type**: escolha o plano desejado (veja observações abaixo)

### 3. Variáveis de ambiente

Em **Environment → Add Environment Variable**, adicione uma a uma
(os valores estão em `deploy_env.txt`):

| Nome | Valor |
|---|---|
| `TELEGRAM_BOT_TOKEN` | (do `deploy_env.txt`) |
| `ALLOWED_TELEGRAM_IDS` | `8871523100` |
| `TIMEZONE` | `America/Sao_Paulo` |
| `GOOGLE_CALENDAR_ID` | `thiagofbg52@gmail.com` |
| `REMINDER_LEAD_MINUTES` | `30` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | (o JSON gigante de uma linha) |

> 💡 **Alternativa mais limpa** para o JSON: em **Secret Files**, crie um arquivo
> chamado `service_account.json` com o conteúdo do arquivo local. Depois use
> `GOOGLE_SERVICE_ACCOUNT_FILE=/etc/secrets/service_account.json` no lugar de
> `GOOGLE_SERVICE_ACCOUNT_JSON`.

### 4. Deploy

Clique em **Create Web Service**. O Render vai instalar e iniciar o bot.
Pronto — com o PC desligado, os lembretes continuam chegando. 🎉

### ⚠️ Sobre planos e o "sono"

- **Web Service gratuito**: o serviço **dorme após ~15 min sem acesso**. Como o
  bot só faz chamadas de saída, ele pode dormir e parar de avisar.
  - Solução: crie um monitor grátis no **https://uptimerobot.com** apontando para
    a URL do seu serviço a cada 5 min. Assim ele não dorme.
- **Background Worker** (pago, ~US$ 7/mês): não dorme e é o mais confiável.
- **Web Service pago (Starter)**: também não dorme.

---

## Opção B — Railway

1. Conta em **https://railway.app** (entra com GitHub).
2. *New Project → Deploy from GitHub repo* → escolha `agenda-telegram`.
3. Em **Variables**, cole as mesmas variáveis da tabela acima.
4. Railway detecta o `Procfile`/`Dockerfile` e roda sozinho.

> Railway dá créditos iniciais e depois é pago por uso (geralmente bem barato para
> um bot pequeno).

---

## Opção C — Fly.io

1. Conta em **https://fly.io**.
2. Instale o `flyctl` e rode, dentro do projeto:
   ```bash
   fly launch
   fly secrets set TELEGRAM_BOT_TOKEN="..." ALLOWED_TELEGRAM_IDS="..." \
     TIMEZONE="America/Sao_Paulo" GOOGLE_CALENDAR_ID="thiagofbg52@gmail.com" \
     GOOGLE_SERVICE_ACCOUNT_JSON='...'
   fly deploy
   ```

---

## Como saber se está funcionando na nuvem

1. No painel da hospedagem, veja os **Logs**. Deve aparecer:
   `Bot iniciado como @mini_thiago_bot`
2. Envie `/start` no Telegram — deve responder.
3. Envie `/novo Teste amanhã às 10h` — o evento deve aparecer no seu Google Calendar.

## Se aparecer erro `Conflict: terminated by other getUpdates request`

Significa que **dois bots** estão rodando ao mesmo tempo (o do seu PC e o da nuvem).
Pare o do seu PC (feche a janela/processo do `run.bat`) ou desligue o da nuvem.
**Só pode existir um rodando por vez.**

---

## Checklist final

- [ ] Projeto no GitHub (privado)
- [ ] Serviço criado na hospedagem
- [ ] Variáveis de ambiente configuradas
- [ ] Logs mostram "Bot iniciado como @mini_thiago_bot"
- [ ] `/start` responde no Telegram
- [ ] Bot do PC **parado** (para não dar conflito)
