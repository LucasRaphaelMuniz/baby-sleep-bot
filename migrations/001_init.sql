-- baby-sleep-bot — schema inicial (Supabase / Postgres)
-- Rode no SQL Editor do seu projeto Supabase.

-- Cuidadores (você e sua companheira). phone em formato E.164.
create table if not exists caregivers (
    id          uuid primary key default gen_random_uuid(),
    name        text,                       -- opcional (pode ser preenchido depois)
    phone       text not null unique,       -- E.164, ex: +5511999999999
    created_at  timestamptz not null default now()
);

-- Bebês. A idade é derivada de birth_date em runtime.
create table if not exists children (
    id                     uuid primary key default gen_random_uuid(),
    name                   text not null,
    birth_date             date not null,
    timezone               text not null default 'America/Sao_Paulo',
    reminder_lead_minutes  int,  -- override opcional do default do config
    created_at             timestamptz not null default now()
);

-- Relação muitos-para-muitos: vários cuidadores por bebê.
create table if not exists caregiver_children (
    caregiver_id  uuid not null references caregivers(id) on delete cascade,
    child_id      uuid not null references children(id)   on delete cascade,
    primary key (caregiver_id, child_id)
);

-- Sonecas e sono noturno. ended_at IS NULL = sono em andamento.
create table if not exists sleep_sessions (
    id            uuid primary key default gen_random_uuid(),
    child_id      uuid not null references children(id) on delete cascade,
    caregiver_id  uuid references caregivers(id),       -- quem registrou
    kind          text not null check (kind in ('nap', 'night')),
    started_at    timestamptz not null,
    ended_at      timestamptz,
    location      text check (location in ('crib','arms','stroller','car','breast')),
    difficulty    text check (difficulty in ('easy','hard','only_held','only_motion')),
    created_at    timestamptz not null default now()
);

-- Garante no máximo UM sono em andamento por bebê (regra de negócio no banco).
create unique index if not exists one_open_session_per_child
    on sleep_sessions (child_id) where ended_at is null;

create index if not exists idx_sessions_child_started
    on sleep_sessions (child_id, started_at desc);

-- Mamadas.
create table if not exists feedings (
    id            uuid primary key default gen_random_uuid(),
    child_id      uuid not null references children(id) on delete cascade,
    caregiver_id  uuid references caregivers(id),
    fed_at        timestamptz not null,
    kind          text not null default 'breast' check (kind in ('breast','bottle','solid')),
    note          text,
    created_at    timestamptz not null default now()
);

create index if not exists idx_feedings_child_fed
    on feedings (child_id, fed_at desc);

-- Despertares noturnos (pertencem a um sono do tipo 'night').
create table if not exists night_wakings (
    id                uuid primary key default gen_random_uuid(),
    sleep_session_id  uuid not null references sleep_sessions(id) on delete cascade,
    woke_at           timestamptz not null,
    reason            text check (reason in ('feed','comfort','unknown')),
    back_at           timestamptz,
    created_at        timestamptz not null default now()
);

-- Cache das janelas de vigília: controla quais lembretes já foram enviados
-- (idempotência do polling de notificações).
create table if not exists wake_windows (
    id                     uuid primary key default gen_random_uuid(),
    child_id               uuid not null references children(id) on delete cascade,
    since_session_id       uuid references sleep_sessions(id) on delete cascade,
    window_start           timestamptz not null,
    close_ideal            timestamptz not null,
    close_max              timestamptz not null,
    reminder_notified_at   timestamptz,
    overtired_notified_at  timestamptz,
    created_at             timestamptz not null default now()
);

create index if not exists idx_wake_windows_child
    on wake_windows (child_id, window_start desc);
