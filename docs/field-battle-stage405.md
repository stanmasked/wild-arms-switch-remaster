# Stage405 — persist confirmed ARM rewards across a cold launch

Base: [Stage404 / PR #79](https://github.com/stanmasked/wild-arms-switch-remaster/pull/79).

## Behavior

The experimental ARM session now loads and saves its confirmed outcome history and EXP/Gella balance through an independent two-slot journal:

`sdmc:/switch/wild_arms_field/arm-training-progress.a`
`sdmc:/switch/wild_arms_field/arm-training-progress.b`

- No reward is written while the Victory preview is pending. Only the B-close result can be committed.
- A confirmed Victory persists its history and the actual credited EXP/Gella.
- A later retreat writes a new generation while preserving the already earned balance.
- A fresh process loads only a fully validated journal. Missing or corrupt data does not mutate the default session.
- Ammunition, battle HP, cursor, edge latches and pending Victory preview remain volatile; a fresh ARM encounter starts from its demo defaults.
- The regular `battle-progress.a/.b` journal and WAFS field-save slots are separate and must remain untouched by this path.
- The normal non-experimental NRO still builds without enabling the ARM feature.

## Tests

Native regression coverage models two session lifetimes and a real journal round trip:
1. A Victory frame shows the pending offer but creates no save.
2. B confirms the Victory and writes generation 1 with 1 win, 8 EXP and 12 Gella.
3. A new default ARM session restores the persisted account but starts with full 3/3 ammunition and a fresh demo battle.
4. A subsequent B retreat writes generation 2, preserving 8 EXP / 12 Gella and updating the outcome history.
5. The ordinary battle journal remains missing, demonstrating namespace isolation.

The NeXium workflow adds a fifth independent guest process that reuses the exact SDMC from the fourth process. The strict auditor verifies both CRC-protected WABJ/WABR generations and checks the actual post-cold-boot EXP/Gella and retreat-history pixels.

## Scope and limitations

This is still a ROM-free experimental battle prototype. The journal is separate from the field save and is not an implementation of the original PlayStation game's save format or economy. The NeXium cold-boot workflow must pass before claiming guest persistence is verified; no physical Switch result is implied.
