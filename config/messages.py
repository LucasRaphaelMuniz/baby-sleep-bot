"""Textos das respostas do bot (pt-BR).

Centralizados aqui para facilitar ajustes e tradução sem caçar strings pelo
código. Mensagens que dependem de dados são funções; as fixas são constantes.
"""

COMMANDS_HELP = (
    "📋 *Comandos*\n"
    "1 — dormiu (soneca)\n"
    "2 — acordou\n"
    "3 — mamou\n"
    "4 — status\n"
    "5 — noite\n"
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


def ask_partner(name: str) -> str:
    return (
        f"Pronto, {name} cadastrada! ✅\n\n"
        "Quer adicionar *outro cuidador* (ex: sua companheira)?\n"
        "Envie o número com DDI e DDD (ex: +5511999999999) ou responda *não*."
    )


PARTNER_INVALID = (
    "Número inválido. Envie no formato +5511999999999 ou responda *não*."
)


def partner_added(phone: str, name: str) -> str:
    return (
        f"Cuidador {phone} adicionado à {name}! 👨‍👩‍👧\n"
        "Quando essa pessoa mandar a primeira mensagem, já cai direto no app.\n\n"
        + COMMANDS_HELP
    )


def onboarding_done(name: str) -> str:
    return f"Tudo certo com a {name}! 👶\n\n" + COMMANDS_HELP


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
