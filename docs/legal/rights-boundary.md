# Frontière juridique — FONBSB Non-Drama

Statut au 13 août 2026 : **`LICENSE_BLOCKED`**.

## Périmètre visé

- langue : fongbe, code ISO 639-3 `fon` ;
- source désignée par l’opérateur : FCBH/Bible.is `FONBSB` ;
- production : **Non-Drama uniquement** ;
- contenu visé : Nouveau Testament, pilote Marc ;
- usage envisagé : paires audio–transcription de 15 secondes maximum pour de futurs travaux ASR/TTS ;
- destination envisagée : dataset Hugging Face privé `VynoDePal/n-x-fon-bible-15s`.

## Constat vérifiable

Les [conditions générales de Faith Comes By Hearing](https://www.faithcomesbyhearing.com/terms), modifiées le 4 mai 2026, indiquent que le texte, l’audio et les autres contenus sont protégés et qu’aucun droit non expressément accordé ne l’est implicitement. Elles limitent l’écoute ou certains téléchargements à la fonctionnalité prévue et interdisent notamment l’extraction, l’adaptation, la republication et la distribution hors autorisation écrite.

Les [conditions Bible Brain](https://www.faithcomesbyhearing.com/bible-brain/terms-conditions) précisent que le contenu peut provenir de tiers, que les droits sont réservés et que l’accès utilisateur est personnel et non commercial. La [licence développeur Bible Brain](https://www.faithcomesbyhearing.com/bible-brain/license) gouverne l’usage de l’API, mais aucune preuve disponible dans ce projet n’accorde l’entraînement ML ni la redistribution de dérivés audio FONBSB.

Une page Bible.is accessible publiquement marque elle-même le contenu « Copyrighted Material ». La gratuité d’écoute, la présence d’un bouton Non-Drama, une API, un téléchargement MP3 autorisé pour l’écoute, ou la confidentialité du dépôt cible ne valent pas licence d’apprentissage automatique.

## Condition de déverrouillage

Avant la première lecture d’un fichier FONBSB réel, le registre doit contenir trois accords indépendants à l’état `approved` :

1. droit d’utiliser et transformer l’enregistrement audio Non-Drama exact ;
2. droit d’utiliser et transformer la traduction/transcription fongbe exacte ;
3. droit d’utiliser ces deux actifs pour l’apprentissage automatique.

Le registre doit aussi préciser la distribution autorisée (`none`, `private` ou `public`), les usages, les dates, une référence de permission et le SHA-256 du document reçu. L’autorisation de publication est revalidée séparément de l’autorisation d’ingestion.

## Actions interdites dans l’état actuel

- aspirer Bible.is, capturer un flux ou contourner un mécanisme d’accès ;
- utiliser les timings d’une édition Drama comme vérité terrain Non-Drama ;
- commiter un texte biblique, un audio, un jeton, un document de permission ou un chemin privé ;
- créer ou alimenter le dataset Hub avec du contenu protégé ;
- considérer le statut privé comme une solution au copyright.

Le code, les tests synthétiques et la documentation peuvent progresser. Les premiers artefacts réels autorisés devront être traités localement, avec provenance et contrôle d’intégrité, puis le pilote Marc devra être validé avant extension au Nouveau Testament.
