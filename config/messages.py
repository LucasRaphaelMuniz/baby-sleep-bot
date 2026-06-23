"""Textos das respostas do bot (pt-BR).

Centralizados aqui para facilitar ajustes e tradução sem caçar strings pelo
código. Mensagens que dependem de dados são funções; as fixas são constantes.
"""

COMMANDS_HELP = (
    "📋 *Comandos*\n"
    "1 — dormiu (soneca)\n"
    "2 — acordou\n"
    "3 — mamou / mamou e dormiu\n"
    "4 — despertou e dormiu de novo (noite, sem mamar)\n"
    "5 — sono da noite\n"
    "6 — status\n"
    "0 ou _desfazer_ — desfaz o último registro\n\n"
    "Horário é opcional: `1 14:30` (sem horário, usa a hora atual).\n"
    "Dúvidas? É só escrever normalmente que eu respondo. 🤖"
)

# ── Onboarding ───────────────────────────────────────────────────────
WELCOME_ASK_NAME = (
    "Oi! 👶 Sou o assistente de sono do seu bebê.\n"
    "Pra começar, qual é o *nome* do bebê?"
)


def ask_birth(name: str) -> str:
    return (
        f"Prazer, {name}! 🎉\n"
        "Qual a *data de nascimento*? (DD/MM/AAAA — ex: 03/03/2026)"
    )


BIRTH_INVALID = (
    "Não entendi a data. 🤔 Envie no formato DD/MM/AAAA (ex: 03/03/2026)."
)


def onboarding_done(name: str, pairing_code: str) -> str:
    return (
        f"Tudo certo com a {name}! 👶\n\n"
        "Para adicionar *outro cuidador* (ex: sua companheira), peça pra ela "
        "mandar este código aqui no WhatsApp:\n\n"
        f"🔑 *{pairing_code}*\n\n" + COMMANDS_HELP
    )


AI_UNAVAILABLE = (
    "🤖 Não consegui responder agora — a IA pode estar sem créditos ou "
    "indisponível. Os comandos 1–5 seguem funcionando normalmente."
)


def linked(name: str) -> str:
    return (
        f"✅ Você foi vinculado(a) à {name}! Agora vocês dois compartilham os "
        "mesmos registros.\n\n" + COMMANDS_HELP
    )


# ── Lembretes proativos (cron) ───────────────────────────────────────
def window_reminder(name: str, awake_str: str, close_ideal_str: str) -> str:
    return (
        f"🔔 {name} acordada há {awake_str}. A janela ideal fecha ~{close_ideal_str} "
        "— bom momento pra começar a acalmar. 😴"
    )


def overtired_alert(name: str, close_max_str: str) -> str:
    return (
        f"⚠️ {name} passou da janela de vigília (limite {close_max_str}). "
        "Risco de overtired — o cortisol sobe e fica mais difícil dormir. "
        "Priorizar o sono agora."
    )
