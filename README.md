# 👶 baby-sleep-bot

Assistente de **registro e análise de sono infantil** operado pelo **WhatsApp**,
com lembretes proativos e um assistente de **IA**. Pensado para os pais
acompanharem sonecas, mamadas e despertares no dia a dia — especialmente na
fase da regressão dos 4 meses.

Você manda `1` quando o bebê dorme, `2` quando acorda, e o bot calcula a próxima
**janela de vigília**, avisa quando ela está fechando e alerta sobre risco de
*overtired*. Também dá pra conversar em linguagem natural — inclusive mandando
**áudio** — que a IA transcreve, registra e responde com base nos dados reais.

> Stack: **Python · Flask · Supabase (Postgres) · WhatsApp (Meta Cloud API _ou_ Twilio) · LiteLLM · OpenAI Whisper**.
> Deploy em **Railway**. Licença **MIT**.

---

## ✨ Funcionalidades

- 📲 Registro rápido por comandos numéricos no WhatsApp (feito pra usar com uma
  mão, no escuro, às 3h da manhã).
- 🎙️ **Áudio no WhatsApp**: manda um áudio e a IA transcreve via Whisper e
  responde normalmente — sem precisar digitar.
- 🧮 Cálculo automático da **janela de vigília** por idade (ajusta sozinho
  conforme o bebê cresce).
- 🔔 **Lembrete** quando a janela está fechando + ⚠️ **alerta de overtired**.
- 🌙 **Modo noite**: registra mamadas e despertares (com ou sem mamada) sem
  disparar avisos de madrugada.
- 🛁 **Bedtime com rotina**: sugere horário de dormir + início do ritual + banho.
- 👨‍👩‍👧 **Multiusuário**: os dois cuidadores registram e veem o mesmo estado
  (vinculação por código de pareamento).
- 🤖 **IA especialista** (via LiteLLM — GPT, Claude, Gemini) responde dúvidas,
  analisa o **histórico de vários dias** e registra por linguagem natural.

## 💬 Comandos

| Atalho | Ação |
|---|---|
| `1` | dormiu (soneca) — `1`, `1 14`, `1 14:30`, `1 14 colo trabalho` |
| `2` | acordou (à noite = "bom dia", encerra a noite) |
| `3` | mamou / mamou e dormiu (à noite = despertar com mamada) |
| `4` | despertou e dormiu de novo — noite, **sem** mamar |
| `5` | sono da noite |
| `6` | status atual + próxima janela |
| `9` ou `desfazer` | desfaz o último registro |
| `0` ou `ajuda` | mostra o menu de comandos e dicas |
| _texto ou áudio livre_ | vai para a IA (dúvida ou registro por linguagem natural) |

Locais aceitos: `berço`, `colo`, `carrinho`, `carro`, `peito`.
Dificuldade aceita: `fácil`, `trabalho` (ex.: "deu trabalho pra dormir").

---

## 🚀 Instalação

### Pré-requisitos
- Python **3.11+**
- Conta no [Supabase](https://supabase.com) (banco Postgres grátis)
- Para o WhatsApp, **um** destes (selecionável por `WHATSAPP_PROVIDER`):
  - [Meta for Developers](https://developers.facebook.com) — número de teste grátis, **ou**
  - [Twilio](https://www.twilio.com) — sandbox de WhatsApp grátis (mais rápido de começar)
- Uma chave de API de LLM — OpenAI (padrão recomendado: `gpt-4o-mini`), Anthropic ou Gemini
- (Opcional) Chave OpenAI para **transcrição de áudio** via Whisper (mesma chave do GPT)

### 1. Clonar e instalar
```bash
git clone https://github.com/LucasRaphaelMuniz/baby-sleep-bot.git
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
   - `migrations/003_pairing_code.sql`
3. Em **Project Settings → API**, copie a `URL` e a `service_role key`.

### 3. Variáveis de ambiente
```bash
cp .env.example .env
```
Preencha o `.env`:
- `SUPABASE_URL` / `SUPABASE_KEY` — do passo anterior.
- `LLM_MODEL` + a chave do provedor (ex.: `OPENAI_API_KEY` para `openai/gpt-4o-mini`).
- `WHATSAPP_PROVIDER` (`meta` ou `twilio`) + as variáveis do provedor escolhido
  (ver seção **Conectar o WhatsApp** abaixo).
- `TIMEZONE` (default `America/Sao_Paulo`).

### 4. Rodar local
```bash
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

| Provedor | `WHATSAPP_PROVIDER` | Webhook |
|---|---|---|
| Meta Cloud API | `meta`   | `…/webhook/whatsapp` |
| Twilio (sandbox) | `twilio` | `…/webhook/twilio` |

### Opção A — Meta Cloud API

1. Em [developers.facebook.com](https://developers.facebook.com) → **Create App**
   → tipo **Business** → adicione o produto **WhatsApp**.
2. Na seção **WhatsApp → API Setup**, anote:
   - **Phone number ID** → `WHATSAPP_PHONE_NUMBER_ID`
   - **Access token** → `WHATSAPP_TOKEN`
   - **App Secret** (App Settings → Basic) → `WHATSAPP_APP_SECRET`
3. Em **WhatsApp → Configuration → Webhook**, configure:
   - **Callback URL:** `https://<seu-app>.up.railway.app/webhook/whatsapp`
   - **Verify token:** o valor que você pôs em `WHATSAPP_VERIFY_TOKEN`
   - **Subscribe** ao campo **messages**.

### Opção B — Twilio (sandbox)

Mais rápido de começar. O número do sandbox é compartilhado (`+1 415 523 8886`);
para rodar junto com outro bot, use uma **segunda conta Twilio**.

1. No Console do Twilio: **Messaging → Try it out → Send a WhatsApp message**.
2. No `.env` / Railway: `WHATSAPP_PROVIDER=twilio`, `TWILIO_ACCOUNT_SID`,
   `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM=whatsapp:+14155238886`.
3. Em **Sandbox settings → "When a message comes in"**, coloque
   `https://<seu-app>.up.railway.app/webhook/twilio` (método **POST**).
4. Cada cuidador manda o `join <palavra-do-sandbox>` para o número e então
   conversa normalmente (inicia o onboarding).

> **Nota:** a validação de assinatura do Twilio está desligada por padrão
> (`TWILIO_VALIDATE=false`) — o sandbox não envia assinatura válida. Para
> produção com número dedicado, mude para `TWILIO_VALIDATE=true`.

### ⚠️ Janela de 24h e os lembretes proativos
O WhatsApp só permite mensagem livre dentro de 24h após a última mensagem do
usuário. Como os pais registram eventos com frequência, a janela fica aberta e
os lembretes passam normalmente. O primeiro lembrete da manhã pode ser bloqueado
se ninguém mandou nada nas últimas 24h — nesse caso, cadastre templates de
lembrete na Meta.

---

## ☁️ Deploy no Railway

### Serviço web
- Crie um projeto no Railway a partir do repositório.
- O [`Procfile`](Procfile) já define: `web: gunicorn wsgi:app --bind 0.0.0.0:$PORT`.
- Adicione todas as variáveis do `.env` em **Variables**.

### Cron de lembretes
O cron é configurado via serviço externo (ex.: [cron-job.org](https://cron-job.org),
gratuito) chamando o endpoint HTTP do próprio app:

1. Crie um job no cron-job.org:
   - **URL:** `https://<seu-app>.up.railway.app/cron/reminders`
   - **Método:** `POST`
   - **Frequência:** a cada 2 minutos
   - **Header:** `X-Cron-Secret: <sua-senha>`
2. No Railway → Variables, adicione:
   - `CRON_SECRET=<mesma-senha>`
   - `WHATSAPP_PROVIDER=twilio` (ou `meta`)

O endpoint verifica quem está acordado e dispara lembrete / alerta de overtired.
É idempotente (estado na tabela `wake_windows`), não duplica avisos.

---

## 🔧 Customização

### Ajustar as janelas por idade
Edite [`config/wake_windows.yaml`](config/wake_windows.yaml) — sem tocar no código:
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
LLM_MODEL=openai/gpt-4o-mini      # recomendado: custo-benefício e qualidade
OPENAI_API_KEY=sk-...

# ou:
LLM_MODEL=anthropic/claude-haiku-4-5-20251001
ANTHROPIC_API_KEY=...
```

### Transcrição de áudio (Whisper)
Funciona automaticamente se `OPENAI_API_KEY` estiver configurada. Custo:
~$0,006/min de áudio. Para desativar, não configure a chave OpenAI (o webhook
ignora áudios silenciosamente).

### Traduzir / mudar os textos
Todas as respostas estão em [`config/messages.py`](config/messages.py).

---

## 🗂️ Estrutura

```
app/
  core/          parser.py, wake_window.py, events.py, history.py  (regras puras)
  ai/            agent.py, tools.py                                 (LiteLLM + tool use)
  notifications/ reminders.py, sender.py, meta_client.py, twilio_client.py
  routes/        webhook.py   (/webhook/twilio, /webhook/whatsapp, /cron/reminders)
  handler.py     orquestrador (onboarding · pareamento · comandos · IA)
  db.py          repositório Supabase
  config.py      carregamento do YAML de configuração
  server.py      app factory Flask (ProxyFix para Railway)
config/          wake_windows.yaml, messages.py
migrations/      001_init.sql, 002_onboarding.sql, 003_pairing_code.sql
scripts/         poll_reminders.py   (entrypoint CLI alternativo ao endpoint HTTP)
tests/           114 testes (sem dependências externas)
```

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
