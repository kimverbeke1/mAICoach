"""
generate_project_map.py — genereert automatisch een overzicht (PROJECT_MAP.md)
van alle Python-bestanden in het project, op basis van hun module-docstring
en top-level functie-/class-definities.

Gebruik (lokaal, in PowerShell, vanuit de root van je mAICoach-repo):

    python generate_project_map.py

Dit maakt/overschrijft PROJECT_MAP.md in de huidige map, met voor elk
.py-bestand:
  - het relatieve pad
  - de module-docstring (indien aanwezig) als "doel"
  - de lijst van top-level functies en classes (zodat je snel ziet wat
    een bestand aanbiedt zonder het te moeten openen)

Mappen die genegeerd worden: .git, __pycache__, venv, .venv, node_modules.

Geen externe dependencies nodig — enkel de Python-standaardbibliotheek
(ast, pathlib), dus dit werkt overal waar Python 3.8+ geïnstalleerd is.
"""
import ast
from pathlib import Path

IGNORE_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules", ".streamlit"}


def get_module_summary(path: Path) -> dict:
    """
    Parseert één .py-bestand en geeft een dict terug met:
      - docstring: de module-docstring, of None
      - functions: lijst van top-level functienamen
      - classes: lijst van top-level classnamen
      - imports: lijst van top-level geïmporteerde modules (enkel de namen,
        handig om snel te zien welke andere eigen bestanden dit bestand
        gebruikt)
    Bij een SyntaxError (bv. een kapot of half-geschreven bestand) wordt
    een dict met een 'error'-sleutel teruggegeven zodat het script niet
    crasht en je meteen ziet welk bestand problematisch is.
    """
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"error": f"SyntaxError: {e}"}

    docstring = ast.get_docstring(tree)
    functions, classes, imports = [], [], []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    return {
        "docstring": docstring,
        "functions": functions,
        "classes": classes,
        "imports": imports,
    }


def first_line(text: str) -> str:
    """Geeft enkel de eerste, betekenisvolle regel van een docstring terug (korte samenvatting)."""
    if not text:
        return "(geen docstring gevonden — doel onbekend)"
    for line in text.strip().splitlines():
        line = line.strip().lstrip("—-").strip()
        if line:
            return line
    return "(lege docstring)"


def build_project_map(root: Path) -> str:
    """Bouwt de volledige Markdown-inhoud van PROJECT_MAP.md."""
    py_files = sorted(
        p for p in root.rglob("*.py")
        if not any(part in IGNORE_DIRS for part in p.parts)
    )

    lines = [
        "# Project Map — automatisch gegenereerd\n",
        f"Totaal aantal Python-bestanden: {len(py_files)}\n",
        "> Gegenereerd met `generate_project_map.py`. Herrun dit script na "
        "grote wijzigingen om dit overzicht up-to-date te houden.\n",
    ]

    # Groepeer per map, zodat AICoach/ en PadelAnalysis/ apart staan
    by_folder: dict[str, list[Path]] = {}
    for p in py_files:
        folder = str(p.parent.relative_to(root)) if p.parent != root else "(root)"
        by_folder.setdefault(folder, []).append(p)

    for folder in sorted(by_folder):
        lines.append(f"\n## 📁 {folder}\n")
        for p in by_folder[folder]:
            info = get_module_summary(p)
            lines.append(f"### `{p.name}`")
            if "error" in info:
                lines.append(f"⚠️ **{info['error']}**\n")
                continue
            lines.append(f"- **Doel:** {first_line(info['docstring'])}")
            if info["classes"]:
                lines.append(f"- **Classes:** {', '.join(info['classes'])}")
            if info["functions"]:
                lines.append(f"- **Functies:** {', '.join(info['functions'])}")
            own_imports = [
                i for i in info["imports"]
                if not i.startswith((
                    "os", "sys", "re", "time", "json", "pathlib", "typing",
                    "datetime", "streamlit", "pandas", "numpy", "requests",
                    "firebase_admin", "google", "openai", "plotly",
                ))
            ]
            if own_imports:
                lines.append(f"- **Gebruikt eigen modules:** {', '.join(sorted(set(own_imports)))}")
            lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    root = Path(__file__).parent
    content = build_project_map(root)
    out_path = root / "PROJECT_MAP.md"
    out_path.write_text(content, encoding="utf-8")
    print(f"Klaar! {out_path} is aangemaakt/bijgewerkt.")
