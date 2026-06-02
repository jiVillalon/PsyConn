"""Revierte las correcciones BIDS (§5.2 TaskName, §5.3 B0Field*) en ds006072.

Justo lo contrario de los chunks §5.2.4 y §5.3.3 de PsiloConn_1.4.qmd:

  1. Restaura `TaskName` en cada `*_bold.json` al valor "sucio" derivado
     del `ProtocolName` DICOM original. Reproduce la transformación que
     aplica dcm2niix: `re.sub(r'[^A-Za-z0-9]', '', ProtocolName)`. Esto
     deshace la sustitución del chunk §5.2.4, que había puesto la
     etiqueta BIDS limpia (e.g. "BOLDREST1") en su lugar.

  2. Elimina `B0FieldSource` de cada `*_bold.json` (lo había añadido el
     chunk §5.3.3).

  3. Elimina `B0FieldIdentifier` de cada `fmap/*_epi.json` (lo había
     añadido el chunk §5.3.3).

Quirúrgico: solo toca estos tres campos. Indentación (`\t` en fmap,
4 espacios en func), saltos de línea (`\n`), precisión numérica y orden
del resto de claves se preservan exactamente (sustitución regex sobre
el texto crudo en bytes, mismo enfoque que los chunks originales).

Idempotente: si el JSON ya está revertido (TaskName ya coincide con la
versión sucia y los B0Field* ya no existen) no se toca.

Usage:
    python D:/ProfessionalProyects/PsyConn/src/python/revert_bids_correction.py --dry-run
    python D:/ProfessionalProyects/PsyConn/src/python/revert_bids_correction.py --execute
"""

from __future__ import annotations

import argparse
import functools
import json
import re
import sys
from pathlib import Path

print = functools.partial(print, flush=True)

BIDS = Path("F:/JIVillL/openneuro/ds006072")

# Misma sanitización que dcm2niix aplica para derivar TaskName del
# ProtocolName DICOM: conservar solo [A-Za-z0-9].
PROTOCOL_TO_TASKNAME = re.compile(r"[^A-Za-z0-9]")

# Captura el valor actual del TaskName en el texto crudo del JSON.
TASKNAME_RE = re.compile(r'("TaskName"\s*:\s*)"([^"]*)"')


def revert_taskname(text: str, original: str) -> tuple[str, str | None]:
    """Restaura TaskName=original. Devuelve (new_text, valor_previo|None).

    Si no hay TaskName o ya coincide con `original`, devuelve el texto
    intacto y `None` como valor previo.
    """
    m = TASKNAME_RE.search(text)
    if not m:
        return text, None
    if m.group(2) == original:
        return text, None
    new_text = TASKNAME_RE.sub(rf'\1"{original}"', text, count=1)
    return new_text, m.group(2)


def strip_json_field(text: str, field: str) -> tuple[str, bool]:
    """Elimina un campo de un JSON preservando el resto del formato.

    Soporta los tipos de valor que escriben los chunks §5.3.3: arrays
    [...], strings "...", números, true/false/null. Maneja tanto la
    forma `, "field": value` (campo precedido por coma — el caso
    habitual cuando está al final del bloque, como aquí) como
    `"field": value,` (campo seguido por coma, defensivo).
    """
    if f'"{field}"' not in text:
        return text, False

    value = r'(?:\[[^\[\]]*\]|"[^"]*"|-?\d+(?:\.\d+)?|true|false|null)'

    # Forma 1: con coma precedente (campo no es el primero del bloque).
    pat1 = rf',\s*\n[ \t]*"{re.escape(field)}"\s*:\s*{value}'
    new_text, n = re.subn(pat1, "", text, count=1, flags=re.DOTALL)
    if n == 1:
        return new_text, True

    # Forma 2: con coma posterior (defensiva).
    pat2 = rf'"{re.escape(field)}"\s*:\s*{value},?\s*\n[ \t]*'
    new_text, n = re.subn(pat2, "", text, count=1, flags=re.DOTALL)
    if n == 1:
        return new_text, True

    return text, False


def revert_bold_json(json_path: Path, dry_run: bool) -> dict:
    """Aplica el revert a un *_bold.json. Devuelve un dict-resumen."""
    raw = json_path.read_bytes()
    text = raw.decode("utf-8")
    parsed = json.loads(text)

    info: dict = {
        "file": json_path.name,
        "taskname_before": parsed.get("TaskName"),
        "taskname_after": None,
        "b0source_removed": False,
        "changed": False,
        "skipped_reason": None,
    }

    protocol = parsed.get("ProtocolName") or parsed.get("SeriesDescription")
    if protocol is None:
        info["skipped_reason"] = "sin ProtocolName ni SeriesDescription"
        return info

    original_taskname = PROTOCOL_TO_TASKNAME.sub("", protocol)

    if text.count('"TaskName"') > 1:
        raise RuntimeError(
            f"Multiple ocurrencias literales de \"TaskName\" en {json_path}; "
            "no se puede sustituir con seguridad")

    new_text, prev_value = revert_taskname(text, original_taskname)
    if prev_value is not None:
        info["taskname_after"] = original_taskname
        info["changed"] = True

    new_text, removed = strip_json_field(new_text, "B0FieldSource")
    if removed:
        info["b0source_removed"] = True
        info["changed"] = True

    if not info["changed"]:
        info["skipped_reason"] = "ya revertido"
        return info

    check = json.loads(new_text)  # ValueError -> burbujea con contexto
    if check.get("TaskName") != original_taskname:
        raise RuntimeError(
            f"Post-revert TaskName mismatch en {json_path}: "
            f"obtuvo {check.get('TaskName')!r}, "
            f"esperaba {original_taskname!r}")
    if "B0FieldSource" in check:
        raise RuntimeError(f"B0FieldSource sigue presente en {json_path}")

    if not dry_run:
        json_path.write_bytes(new_text.encode("utf-8"))
    return info


def revert_fmap_json(json_path: Path, dry_run: bool) -> dict:
    """Aplica el revert a un fmap *_epi.json. Devuelve un dict-resumen."""
    raw = json_path.read_bytes()
    text = raw.decode("utf-8")

    info: dict = {
        "file": json_path.name,
        "b0id_removed": False,
        "changed": False,
        "skipped_reason": None,
    }

    new_text, removed = strip_json_field(text, "B0FieldIdentifier")
    if not removed:
        info["skipped_reason"] = "B0FieldIdentifier ausente (ya revertido)"
        return info

    info["b0id_removed"] = True
    info["changed"] = True

    check = json.loads(new_text)
    if "B0FieldIdentifier" in check:
        raise RuntimeError(f"B0FieldIdentifier sigue presente en {json_path}")

    if not dry_run:
        json_path.write_bytes(new_text.encode("utf-8"))
    return info


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="Solo simular; no toca ficheros.")
    g.add_argument("--execute", action="store_true",
                   help="Ejecutar el revert sobre los JSON sidecars.")
    args = ap.parse_args()

    print("=" * 78)
    print("Revert correcciones BIDS (§5.2 TaskName + §5.3 B0Field*)")
    print(f"BIDS root: {BIDS}")
    print(f"Modo: {'dry-run' if args.dry_run else 'EXECUTE'}")
    print("=" * 78)

    bold_jsons = sorted(BIDS.glob("sub-*/ses-*/func/*_bold.json"))
    fmap_jsons = sorted(BIDS.glob("sub-*/ses-*/fmap/*_epi.json"))

    bold_changed = bold_skipped = 0
    fmap_changed = fmap_skipped = 0
    errors: list[str] = []

    print(f"\n--- BOLD ({len(bold_jsons)} *_bold.json) ---")
    for jp in bold_jsons:
        try:
            info = revert_bold_json(jp, args.dry_run)
        except (RuntimeError, json.JSONDecodeError) as e:
            errors.append(f"{jp.name}: {e}")
            continue
        if info["changed"]:
            bold_changed += 1
            tn = ""
            if info["taskname_after"] is not None:
                tn = (f" TaskName: {info['taskname_before']!r}"
                      f" -> {info['taskname_after']!r}")
            b0 = " -B0FieldSource" if info["b0source_removed"] else ""
            print(f"  {info['file']}:{tn}{b0}")
        else:
            bold_skipped += 1

    print(f"\n--- FMAP ({len(fmap_jsons)} *_epi.json) ---")
    for jp in fmap_jsons:
        try:
            info = revert_fmap_json(jp, args.dry_run)
        except (RuntimeError, json.JSONDecodeError) as e:
            errors.append(f"{jp.name}: {e}")
            continue
        if info["changed"]:
            fmap_changed += 1
            print(f"  {info['file']}: -B0FieldIdentifier")
        else:
            fmap_skipped += 1

    print("\n" + "=" * 78)
    print(f"BOLD revertidos: {bold_changed}   sin cambios: {bold_skipped}")
    print(f"FMAP revertidos: {fmap_changed}   sin cambios: {fmap_skipped}")
    if errors:
        print(f"\nERRORES ({len(errors)}):")
        for e in errors:
            print(f"  {e}")
    if args.dry_run:
        print("[dry-run] no se ha tocado ningún fichero.")
    else:
        print("Revert completado.")
    print("=" * 78)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main() or 0)
