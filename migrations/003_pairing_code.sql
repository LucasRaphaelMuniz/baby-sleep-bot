-- Código de pareamento: permite um 2º cuidador se vincular ao bebê enviando
-- um código no WhatsApp (captura o número exatamente como o provedor envia,
-- evitando problemas de formato/nono dígito do Brasil).
alter table children add column if not exists pairing_code text;

create unique index if not exists children_pairing_code_idx
    on children (pairing_code) where pairing_code is not null;
