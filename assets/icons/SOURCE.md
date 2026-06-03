# Galerías de iconos de menú (referencia para identificar especies)

Cada `gen<N>/` contiene los menu sprites de esa generación, nombrados por número de
Pokédex (`25.png` = Pikachu), y un `embeddings.npz` con sus huellas ya calculadas
(lo único que necesita el runtime; los PNG no se versionan, ver `.gitignore`).

| Carpeta | Sprites (estilo Bulbagarden) | Cobertura aprox. |
|---------|------------------------------|------------------|
| gen3    | `MS3` (GBA)                  | 1–386 |
| gen4    | `MS3` (DS)                   | 1–493 |
| gen5    | `MS3` (DS)                   | 1–649 |
| gen6    | `MS6` (3DS)                  | 1–721 |
| gen7    | `MS6` (3DS)                  | 1–809 |
| gen8    | `MS8` (Switch SwSh)          | subconjunto |
| gen9    | iconos HOME                  | 1–1025 |

- **Fuente**: [Bulbagarden Archives](https://archives.bulbagarden.net/) — categorías
  "Generation X menu sprites" e iconos HOME. Descargados con el script de
  `pvo/tools` (API de MediaWiki).
- **Regenerar `embeddings.npz`** (si cambias el modelo o los iconos):
  `python -m pvo.tools.build_embeddings --icons assets/icons/gen3 --out assets/icons/gen3/embeddings.npz`
- Los sprites son propiedad de Nintendo/Game Freak; aquí solo como referencia para
  uso personal.
