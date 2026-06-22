-- Estado temporário do onboarding (conversa de cadastro do primeiro uso).
-- Uma linha por telefone enquanto o cadastro não termina; removida ao final.
create table if not exists onboarding_states (
    phone       text primary key,
    step        text not null,              -- awaiting_name | awaiting_birth | awaiting_partner
    baby_name   text,
    child_id    uuid references children(id) on delete cascade,
    updated_at  timestamptz not null default now()
);
