# Carte IcePanel — N-x-Fon

Mise à jour le 13 août 2026 dans le domaine IcePanel `Default domain` (`Xqqv6eZAgTr6xY004anM`). Un squelette existant « BibleSpeech-30s » a été réconcilié avec le périmètre approuvé, sans créer un système concurrent.

## Hiérarchie

- `N-x-Fon Bible 15s Pipeline` — système, `V6TgaVbm88V28xIa8YFc`, état `future` ;
  - `Rights & Provenance Gate` — application, `rdvMSCvAC9ZJExvmUB8t`, état `live` ;
  - `Source Ingestion & Canonicalization` — application, `L7Df0OXwyflR2ix82irp`, état `future` ;
  - `Alignment & 15s Segment Planner` — application, `qdoYahG37XuIH9aouthW`, état `future` ;
  - `Quality Gate & Dataset Builder` — application, `ZFELXd8GCHlSK910BM0E`, état `future` ;
  - `Curated Corpus Store` — stockage, `8gHhXOzab5EEsBL8Mz42`, état `future`.
- `Hugging Face Hub` — système externe partagé, `omWe4Uya27VK2JTvCZIe`, état `live`.

## Connexions

| Origine | Connexion | Cible | État |
|---|---|---|---|
| Rights & Provenance Gate | Authorizes local ingest | Source Ingestion & Canonicalization | live |
| Source Ingestion & Canonicalization | Supplies canonical source inventory | Alignment & 15s Segment Planner | future |
| Alignment & 15s Segment Planner | Supplies bounded segment plans | Quality Gate & Dataset Builder | future |
| Rights & Provenance Gate | Authorizes distribution | Quality Gate & Dataset Builder | future |
| Quality Gate & Dataset Builder | Writes accepted clips and evidence | Curated Corpus Store | future |
| Quality Gate & Dataset Builder | Publishes authorized private dataset | Hugging Face Hub | future |

La dernière connexion cible `VynoDePal/n-x-fon-bible-15s`, mais reste volontairement future pendant `LICENSE_BLOCKED`.

## Décisions acceptées

- ADR-004 `uz5QwAynnsnNWZu2NOVP` — Three independent rights grants fail closed ;
- ADR-005 `ppo83vjTDF5cIubPF0f7` — Non-Drama alignment is independently derived ;
- ADR-006 `iHKgRbbHFS3fu8tYaVBQ` — Segment boundaries are sample-exact and capped at 15 seconds ;
- ADR-007 `dgDKOa1GBNJ4uRAxfGTb` — Preserve Fongbe tone and Unicode integrity ;
- ADR-008 `DWJXHkGXppQtqwEry8mH` — Hugging Face releases are chapter-split and rights-gated.

Tous ces ADR sont à l’état `accepted` dans IcePanel. La carte décrit l’architecture cible ; elle ne prétend pas que la source FCBH, le corpus réel ou le dataset Hub existent déjà.
