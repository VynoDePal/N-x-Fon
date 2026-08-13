# N-x-Fon

N-x-Fon est un pipeline reproductible de segmentation audio–transcription en fongbe (`fon`) pour des clips destinés à la recherche ASR/TTS. L’Alpha technique cible le Nouveau Testament FONBSB **Non-Drama**, avec une durée maximale mesurée de 15,000 secondes. Elle ne contient, ne télécharge et ne publie actuellement aucun audio ni texte biblique.

## Statut : `LICENSE_BLOCKED`

Le code est utilisable sur des fixtures synthétiques, mais le contenu FCBH/Bible.is reste juridiquement bloqué. Les [conditions FCBH](https://www.faithcomesbyhearing.com/terms) réservent les droits non expressément accordés, interdisent notamment de copier ou extraire l’audio du service et exigent un accord écrit pour les usages non prévus. Les [conditions Bible Brain](https://www.faithcomesbyhearing.com/bible-brain/terms-conditions) limitent l’accès au contenu à des usages personnels définis et signalent que des ayants droit tiers peuvent imposer d’autres restrictions. Une page Bible.is marque en outre le contenu comme protégé par copyright.

Un dépôt GitHub privé ou un dataset Hugging Face privé ne constitue pas une autorisation. Avant toute lecture de fichiers FONBSB réels, il faut une preuve écrite et vérifiable couvrant séparément :

1. les droits sur l’audio Non-Drama exact ;
2. les droits sur la transcription exacte ;
3. l’usage machine learning et le niveau de redistribution (`none`, `private` ou `public`).

Le pipeline exige le document de permission, son SHA-256, sa période de validité et `machine_learning` dans les usages autorisés. Il échoue fermé avant de lire la source si un seul contrôle manque. Aucune procédure de téléchargement ou de contournement FCBH n’est fournie.

## Installation

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## Vérifier le verrou juridique

Le fichier `config/rights.blocked.example.yaml` décrit l’état initial bloqué :

```bash
nxfon rights validate config/rights.blocked.example.yaml permissions --action ingest
```

Cette commande doit échouer tant qu’une permission réelle n’est pas fournie. Ne remplacez jamais cet état par `approved` sur la seule base du caractère gratuit, accessible ou privé des données.

## Flux local autorisé

Les commandes suivantes ne sont valides qu’après réception des droits et dépôt local légal des fichiers par l’opérateur :

```bash
nxfon ingest /authorized/source/MRK01.wav \
  --rights-file /authorized/rights.yaml \
  --permission-root /authorized/permissions \
  --source-root /authorized/source \
  --output work/MRK01.inventory.json

nxfon segment work/MRK01.tokens.jsonl \
  --rights-file /authorized/rights.yaml \
  --permission-root /authorized/permissions \
  --source-sha256 SOURCE_SHA256 \
  --sample-rate 16000 \
  --output work/MRK01.plans.jsonl

nxfon qc work/MRK01.qc-input.jsonl \
  --rights-file /authorized/rights.yaml \
  --permission-root /authorized/permissions \
  --output work/MRK01.qc.jsonl

nxfon export-hf work/rows.jsonl config/splits.json work/audiofolder \
  --rights-file /authorized/rights.yaml \
  --permission-root /authorized/permissions
```

`export-hf` construit seulement un AudioFolder local et déterministe. La publication distante vers `VynoDePal/n-x-fon-bible-15s` n’est pas activée dans l’Alpha. Les partitions sont assignées au niveau chapitre afin d’éviter les fuites entre clips du même chapitre.

## Garanties techniques

- texte fongbe conservé en original et normalisé en NFC sans suppression des tons ;
- inventaire local sans URL, avec SHA-256 en flux et `ffprobe` sans shell ;
- frontières exactes en échantillons, identifiants déterministes et aucune troncature de mot ;
- WAV mono PCM16 rendu atomiquement ;
- rejet explicite des durées > 15 s, du clipping, du silence excessif, de la musique, du chevauchement et des transcriptions non lexicales ;
- export limité aux clips acceptés, avec provenance et résumé des droits sans contenu du document de permission.

Voir la [conception](docs/superpowers/specs/2026-08-13-n-x-fon-pipeline-design.md) et le [plan d’implémentation](docs/superpowers/plans/2026-08-13-n-x-fon-technical-alpha.md).
