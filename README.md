# 👶 baby-sleep-bot

Assistente de **registro e análise de sono infantil** operado pelo **WhatsApp**,
com lembretes proativos e um assistente de **IA**. Pensado para os pais
acompanharem sonecas, mamadas e despertares no dia a dia — especialmente na
fase da regressão dos 4 meses.

Você manda `1` quando o bebê dorme, `2` quando acorda, e o bot calcula a próxima
**janela de vigília**, avisa quando ela está fechando e alerta sobre risco de
*overtired*. Também dá pra conversar em linguagem natural ("ela mamou às 15h",
"dormiu pouco hoje?") que a IA registra e responde com base nos dados reais.

> Stack: **Python · Flask · Supabase (Postgres) · WhatsApp (Meta Cloud API _ou_ Twilio) · LiteLLM**.
> Deploy em **Railway**. Licença **MIT**.

---

## ✨ Funcionalidades

- 📲 Registro rápido por comandos numéricos no WhatsApp (feito pra usar com uma
  mão, no escuro, às 3h da manhã).
- 🧮 Cálculo automático da **janela de vigília** por idade (ajusta sozinho
  conforme o bebê cresce).
- 🔔 **Lembrete** quando a janela está fechando + ⚠️ **alerta de overtired**.
- 🌙 **Modo noite**: registra mamadas/despertares sem disparar avisos de
  madrugada.
- 🛁 **Bedtime com rotina**: sugere horário de dormir + início do ritual + banho.
- 👨‍👩‍👧 **Multiusuário**: os dois cuidadores registram e veem o mesmo estado.
- 🤖 **IA** (Claude/GPT/Gemini via LiteLLM) responde dúvidas, analisa o
  **histórico de vários dias** e registra por linguagem natural. Ex.: _"resumo
  dos últimos 3 dias"_ ou _"hoje só consigo deitar ela após 20h, qual bedtime?"_.

## 💬 Comandos

| Atalho | Ação |
|---|---|
| `1` | dormiu (soneca) — `1`, `1 14`, `1 14:30`, `1 14 colo trabalho` |
| `2` | acordou (à noite = "bom dia", encerra a noite) |
| `3` | mamou (à noite = despertar noturno) |
| `4` | status atual + próxima janela |
| `5` | noite (sono noturno) |
| `0` ou `desfazer` | desfaz o último registro |
| _texto livre_ | vai para a IA (dúvida ou registro por linguagem natural) |

Locais aceitos: `berço`, `colo`, `carrinho`, `carro`, `peito`.
Dificuldade aceita: `fácil`, `trabalho` (ex.: "deu trabalho pra dormir").

---

## 🚀 Instalação

### Pré-requisitos
- Python **3.11+**
- Conta no [Supabase](https://supabase.com) (banco Postgres grátis)
- Para o WhatsApp, **um** destes (selecionável por `WHATSAPP_PROVIDER`):
  - [Meta for Developers](https://developers.facebook.com) — número de teste grátis
    (número próprio, mas contas novas podem cair em restrição de onboarding), **ou**
  - [Twilio](https://www.twilio.com) — sandbox de WhatsApp grátis (mais rápido de
    começar; o número do sandbox é compartilhado)
- Uma chave de API de LLM — [Anthropic](https://console.anthropic.com) (padrão),
  OpenAI ou Google Gemini

### 1. Clonar e instalar
```bash
git clone https://github.com/<voce>/baby-sleep-bot.git
cd baby-sleep-bot
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Banco de dados (Supabase)
1. Crie um projeto no Supabase.
2. No **SQL Editor**, rode os arquivos de migração na ordem:
   - `migrations/001_init.sql`
   - `migrations/002_onboarding.sql`
3. Em **Project Settings → API**, copie a `URL` e a `service_role key`.

### 3. Variáveis de ambiente
```bash
cp .env.example .env
```
Preencha o `.env`:
- `SUPABASE_URL` / `SUPABASE_KEY` — do passo anterior.
- `LLM_MODEL` + a chave do provedor (ex.: `ANTHROPIC_API_KEY`).
- `WHATSAPP_PROVIDER` (`meta` ou `twilio`) + as variáveis do provedor escolhido
  (ver seção **Conectar o WhatsApp** abaixo).
- `TIMEZONE` (default `America/Sao_Paulo`).

### 4. Rodar local
```bash
# para testar sem validar assinatura da Meta:
WHATSAPP_VALIDATE=false gunicorn wsgi:app        # ou: flask --app wsgi run
```
Verifique a saúde do serviço: `GET http://localhost:8000/health` → `ok`.

### 5. Testes
```bash
pytest
```
Os testes rodam **sem** WhatsApp/Supabase/LLM (tudo é injetado/falso).

---

## 📡 Conectar o WhatsApp

O provedor é escolhido por `WHATSAPP_PROVIDER` (`meta` ou `twilio`). As duas
rotas de webhook coexistem; basta apontar o painel do provedor escolhido para a
rota correspondente:

| Provedor | `WHATSAPP_PROVIDER` | Callback / webhook |
|---|---|---|
| Meta Cloud API | `meta`   | `…/webhook/whatsapp` |
| Twilio (sandbox) | `twilio` | `…/webhook/twilio` |

### Opção A — Meta Cloud API

A [WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api)
da Meta tem **número de teste gratuito** (até 5 destinatários verificados,
suficiente para uso doméstico), com número próprio.

1. Em [developers.facebook.com](https://developers.facebook.com) → **Create App**
   → tipo **Business** → adicione o produto **WhatsApp**.
2. Na seção **WhatsApp → API Setup**, anote:
   - **Phone number ID** (do número de teste) → `WHATSAPP_PHONE_NUMBER_ID`
   - **Access token** → `WHATSAPP_TOKEN`. O token temporário expira em 24h; para
     produção, crie um **System User** (Business Settings) e gere um token
     permanente.
   - Em **App Settings → Basic**, copie o **App Secret** → `WHATSAPP_APP_SECRET`.
3. Adicione os números dos cuidadores em **"To"** (recebem um código de
   verificação) — esses são os destinatários autorizados do número de teste.
4. Em **WhatsApp → Configuration → Webhook**, clique **Edit** e configure:
   - **Callback URL:** `https://<seu-app>.up.railway.app/webhook/whatsapp`
   - **Verify token:** o mesmo valor que você pôs em `WHATSAPP_VERIFY_TOKEN`
   - Após verificar, **Subscribe** ao campo **messages**.
5. Mande qualquer mensagem pelo WhatsApp para o número de teste → o bot inicia o
   **onboarding** (nome e nascimento do bebê + segundo cuidador).

> Para desenvolvimento local, exponha a porta com [ngrok](https://ngrok.com)
> (`ngrok http 8000`) e use a URL gerada como Callback URL.

### Opção B — Twilio (sandbox)

Mais rápido de começar (sem aprovação de conta), mas o número do sandbox é
**compartilhado** (`+1 415 523 8886`) e cada conta Twilio só mantém **um**
sandbox — para rodar junto com outro bot, use uma **segunda conta Twilio** (o
sandbox dela é independente).

1. No Console do Twilio: **Messaging → Try it out → Send a WhatsApp message**.
   Anote o **Account SID**, o **Auth Token** e o número do sandbox.
2. No `.env` / Railway: `WHATSAPP_PROVIDER=twilio`, `TWILIO_ACCOUNT_SID`,
   `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM=whatsapp:+14155238886`.
3. Em **Sandbox settings → "When a message comes in"**, coloque
   `https://<seu-app>.up.railway.app/webhook/twilio` (método **POST**).
4. Cada cuidador manda o `join <palavra-do-sandbox>` para o número e então
   conversa normalmente (inicia o onboarding).

### ⚠️ Janela de 24h e os lembretes proativos
O WhatsApp só permite **mensagem livre dentro de 24h** após a última mensagem do
usuário. Fora disso, apenas **templates pré-aprovados**.

- Durante o dia isso não atrapalha: como vocês registram eventos com frequência,
  a janela de 24h fica aberta e os lembretes passam normalmente.
- O **primeiro lembrete da manhã** pode cair fora da janela se ninguém mandou
  nada nas últimas 24h — nesse caso o envio livre é **bloqueado**. Se isso virar
  problema na prática, cadastre 1–2 **message templates** de lembrete na Meta e
  use-os no `scripts/poll_reminders.py` para os envios fora da janela.

---

## ☁️ Deploy no Railway

O projeto tem **dois processos**: o webhook (web) e o cron de lembretes.

### Serviço web
- Crie um projeto no Railway a partir do repositório.
- O [`Procfile`](Procfile) já define: `web: gunicorn wsgi:app --bind 0.0.0.0:$PORT`.
- Adicione todas as variáveis do `.env` em **Variables**.
- Use o domínio gerado para configurar o webhook da Meta (acima).

### Cron de lembretes
- Adicione um **Cron Job** (ou um segundo serviço) no Railway com:
  - **Comando:** `python -m scripts.poll_reminders`
  - **Schedule:** `*/2 * * * *` (a cada 2 minutos)
- Ele verifica quem está acordado e dispara lembrete / alerta de overtired.
  É idempotente (estado na tabela `wake_windows`), então não duplica avisos.

---

## 🔧 Customização

### Ajustar as janelas por idade
Edite [`config/wake_windows.yaml`](config/wake_windows.yaml) — sem tocar no
código:
```yaml
wake_windows:
  - { up_to_weeks: 17, ideal: 90, max: 120 }   # ~4 meses
  - { up_to_weeks: 26, ideal: 120, max: 150 }
bedtime_window: ["19:00", "20:30"]
reminder_lead_minutes: 20      # antecedência do lembrete
quiet_hours: ["20:30", "06:00"]  # sem avisos nesse período
```

### Trocar o provedor de IA
No `.env`, mude o modelo e a chave correspondente (via LiteLLM):
```bash
LLM_MODEL=openai/gpt-4.1          # ou gemini/gemini-2.0-flash, etc.
OPENAI_API_KEY=...
```

### Traduzir / mudar os textos
Todas as respostas estão em [`config/messages.py`](config/messages.py).

---

## 🗂️ Estrutura

```
app/
  core/          parser.py, wake_window.py, events.py   (regras puras/negócio)
  ai/            agent.py, tools.py                     (LiteLLM + tool use)
  notifications/ reminders.py, meta_client.py           (lembretes)
  routes/        webhook.py                             (webhook /webhook/whatsapp)
  handler.py     orquestrador (onboarding vs comando)
  db.py          repositório Supabase
  config.py      server.py
config/          wake_windows.yaml, messages.py
migrations/      001_init.sql, 002_onboarding.sql
scripts/         poll_reminders.py                      (entrypoint do cron)
tests/           90+ testes (sem dependências externas)
```

Veja [`DESIGN.md`](DESIGN.md) para as decisões de arquitetura.

---

## ⚠️ Aviso

Esta ferramenta **não substitui orientação médica/pediátrica**. As janelas e
sugestões são heurísticas gerais; cada bebê é único. Diante de qualquer sinal de
alerta, procure o pediatra.

## 🤝 Contribuindo

PRs são bem-vindos. Ao contribuir, inclua o sinal-off do
[DCO](https://developercertificate.org/) nos commits (`git commit -s`), o que
mantém a opção de relicenciamento futuro do projeto.

## 📄 Licença

[MIT](LICENSE) © 2026
