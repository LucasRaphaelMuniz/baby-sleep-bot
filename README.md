# 👶 baby-sleep-bot

Assistente de **registro e análise de sono infantil** operado pelo **WhatsApp**,
com lembretes proativos e um assistente de **IA**. Pensado para os pais
acompanharem sonecas, mamadas e despertares no dia a dia — especialmente na
fase da regressão dos 4 meses.

Você manda `1` quando o bebê dorme, `2` quando acorda, e o bot calcula a próxima
**janela de vigília**, avisa quando ela está fechando e alerta sobre risco de
*overtired*. Também dá pra conversar em linguagem natural ("ela mamou às 15h",
"dormiu pouco hoje?") que a IA registra e responde com base nos dados reais.

> Stack: **Python · Flask · Supabase (Postgres) · Twilio (WhatsApp) · LiteLLM**.
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
- Conta no [Twilio](https://www.twilio.com) (sandbox de WhatsApp grátis)
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
- `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_WHATSAPP_FROM`.
- `TIMEZONE` (default `America/Sao_Paulo`).

### 4. Rodar local
```bash
# para testar sem validar assinatura do Twilio:
TWILIO_VALIDATE=false gunicorn wsgi:app          # ou: flask --app wsgi run
```
Verifique a saúde do serviço: `GET http://localhost:8000/health` → `ok`.

### 5. Testes
```bash
pytest
```
Os testes rodam **sem** Twilio/Supabase/LLM (tudo é injetado/falso).

---

## 📡 Conectar o WhatsApp (Twilio)

1. No Console do Twilio: **Messaging → Try it out → Send a WhatsApp message**
   (sandbox). Siga as instruções pra parear seu número.
2. Em **Sandbox settings**, no campo **"When a message comes in"**, coloque a URL
   pública do seu deploy:
   ```
   https://<seu-app>.up.railway.app/webhook/twilio      (método: POST)
   ```
3. Mande qualquer mensagem pro número do sandbox → o bot inicia o **onboarding**
   (pergunta nome e data de nascimento do bebê e oferece adicionar o segundo
   cuidador).

> Para desenvolvimento local, exponha a porta com [ngrok](https://ngrok.com)
> (`ngrok http 8000`) e use a URL gerada no campo acima.

### ⚠️ Rodando junto com outro app no sandbox
O **sandbox do WhatsApp é único por conta Twilio** — um número compartilhado
(`+1 415 523 8886`), **um** webhook e **uma** lista de participantes. Ou seja,
na mesma conta você **não** roda dois bots no sandbox ao mesmo tempo (eles
brigam pelo mesmo número/webhook).

- Para manter outro app (ex.: outro bot já existente) intocado, **crie uma
  segunda conta Twilio** e use o sandbox dela: cada conta tem sandbox
  independente (webhook, `join` e participantes próprios). É grátis.
- Para um **número dedicado** de verdade (sem `join`, mensagem para qualquer
  contato), registre um **WhatsApp Sender** de produção (Twilio + Meta Business
  Manager + verificação do negócio). Mais setup; recomendado ao sair do teste.

### ⚠️ Janela de 24h e os lembretes proativos
O WhatsApp só permite **mensagem livre dentro de 24h** após a última mensagem do
usuário. Fora disso, apenas **templates pré-aprovados**.

- Durante o dia isso não atrapalha: como vocês registram eventos com frequência,
  a janela de 24h fica aberta e os lembretes passam normalmente.
- O **primeiro lembrete da manhã** pode cair fora da janela se ninguém mandou
  nada nas últimas 24h — nesse caso o envio livre é **bloqueado**. Se isso virar
  problema na prática, cadastre 1–2 **message templates** de lembrete no Twilio e
  use-os no `scripts/poll_reminders.py` para os envios fora da janela.

---

## ☁️ Deploy no Railway

O projeto tem **dois processos**: o webhook (web) e o cron de lembretes.

### Serviço web
- Crie um projeto no Railway a partir do repositório.
- O [`Procfile`](Procfile) já define: `web: gunicorn wsgi:app --bind 0.0.0.0:$PORT`.
- Adicione todas as variáveis do `.env` em **Variables**.
- Use o domínio gerado para configurar o webhook do Twilio (acima).

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
  notifications/ reminders.py, twilio_client.py         (lembretes)
  routes/        webhook.py                             (POST /webhook/twilio)
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
