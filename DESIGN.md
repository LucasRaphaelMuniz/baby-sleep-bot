# baby-sleep-bot — Desenho

Bot de registro e análise de sono infantil, operado por WhatsApp, com assistente
de IA. Pensado para uso doméstico e publicação open-source (MIT).

## Stack
- **Interface:** WhatsApp (registro rápido + notificações proativas). Provedor
  selecionável por `WHATSAPP_PROVIDER`: **Meta Cloud API** ou **Twilio** — as duas
  rotas de webhook coexistem; só os lembretes (cron) usam o seletor via `sender.py`.
  Dashboard web read-only fica para uma fase 2.
- **Backend:** Flask + Supabase (Postgres).
- **Deploy:** Railway.
- **IA:** abordagem com *tool use*, via [LiteLLM](https://github.com/BerriAI/litellm)
  (provedor trocável por `.env`; default `anthropic/claude-sonnet-4-6`).

## Comandos do WhatsApp
| Atalho | Ação |
|---|---|
| `1` | dormiu (soneca) |
| `2` | acordou |
| `3` | mamou |
| `4` | status (estado atual + próxima janela) |
| `5` | noite (sono noturno) |
| `0` / `desfazer` | desfaz o último evento |

Texto livre que não casa com comando é roteado para a IA, que responde no próprio
WhatsApp e pode registrar eventos por linguagem natural (tool use).

### Modo noite
Enquanto um sono `5 noite` está aberto, os comandos mudam de significado e
**nenhum aviso é disparado** (não acordamos os pais de madrugada):
- `3 mamou` → registra mamada da noite e conta como 1 despertar (abordagem
  "só mamadas": cada despertar noturno é uma mamada).
- `2 acordou` → encerra a noite = "bom dia": só aqui o dia começa e a 1ª janela
  de vigília é calculada.
- `4 status` → resumo da noite (desde quando, quantos despertares e horários).

### Parsing de hora
- `1` → horário da mensagem (agora)
- `1 14`, `1 14:00`, `1 14h30`, `1 1430` → horário explícito
- Número isolado fora de `0–5` (ex.: `14`) → **erro amigável** pedindo o comando.
  Nunca adivinhamos: registro de sono errado é pior que perguntar.
- Local e dificuldade opcionais (ordem livre): `1 14 colo trabalho`
  (locais: `berço`/`colo`/`carrinho`/`carro`/`peito`; dificuldade: `fácil`/`trabalho`).

## Janela de vigília
- A idade é calculada em runtime a partir da data de nascimento — a janela se
  ajusta sozinha conforme o bebê cresce.
- Faixas idade→vigília ficam em `config/wake_windows.yaml`, editáveis sem tocar
  no código (reutilização por outros usuários).
- Sinais de overtired: passou do máximo da janela ainda acordado.

## Lembretes proativos (2 estágios)
1. **Lembrete** em `T - lead` (default 20 min, ajustável) antes do fechamento
   ideal da janela: hora de iniciar o ritual de acalmar.
2. **Alerta overtired** quando passa do máximo e o bebê continua acordado.

Implementação por **polling via cron** (não agendamento em memória): sobrevive a
redeploy/restart no Railway, é idempotente (estado em `wake_windows.notified_at`)
e cancela sozinho se o bebê dormir.

Lembretes ficam suspensos durante `quiet_hours` **e** sempre que houver um sono
em andamento (especialmente o noturno): janela/lembrete só existem em período de
vigília diurna. Despertares noturnos (mamadas) não iniciam janela.

## Onboarding
No primeiro contato de um número desconhecido, o bot pergunta nome e data de
nascimento do bebê e grava em `children` / `caregivers`.

## Estrutura do repositório
```
config/        wake_windows.yaml (faixas), messages.py (textos pt-BR)
app/
  core/        parser.py, wake_window.py, events.py   (regras puras/negócio)
  routes/      webhook.py                              (webhook /webhook/whatsapp)
  ai/          agent.py, tools.py                      (LiteLLM + tool use)
  notifications/  meta_client.py, twilio_client.py, sender.py, reminders.py
  config.py    db.py
migrations/    001_init.sql
scripts/       poll_reminders.py (entrypoint do cron)
tests/         test_parser.py, test_wake_window.py
```

## Ordem de implementação
1. ✅ **Núcleo puro:** `parser.py` + `wake_window.py` + testes (sem WhatsApp/Supabase).
2. ✅ Migration `001_init.sql` + `db.py` + `events.py`.
3. ✅ Webhook WhatsApp (Meta) + onboarding + comandos 1–5 (`handler.py`, `routes/webhook.py`,
   `server.py`, `config/messages.py`, migration `002_onboarding.sql`).
4. ✅ Camada IA (LiteLLM + tools): `ai/agent.py` (laço de tool use + contexto),
   `ai/tools.py` (6 ferramentas: registrar sono/acordar/mamar, status, histórico
   multi-dia via `core/history.py`, e bedtime com rotina/restrição).
5. ✅ Lembretes (polling 2 estágios) + cron: `notifications/reminders.py`,
   `notifications/meta_client.py`, `scripts/poll_reminders.py`.
6. ✅ README/tutorial + `.env.example` + `.python-version`.
