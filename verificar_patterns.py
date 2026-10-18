"""Verifica los archivos de patrones de XULIA2 (patterns.txt y patterns.<idioma>.txt).

Avisa de:
  - claves repetidas (la segunda pisa a la primera; incluye las líneas "clave=>reemplazo",
    que el cargador lee como un comando con regex ">...");
  - expresiones regulares inválidas;
  - claves que faltan o sobran en un archivo de idioma respecto de patterns.txt (una clave sin
    equivalente en ese idioma se declara con una línea "# sin-equivalente: clave1 clave2");
  - claves sin acción (no hay manejador en _init_command_handlers: el bucle las salta);
  - reglas que capturan la frase de otra (la frase de la regla B la gana una regla A anterior).

Uso:
  python verificar_patterns.py                 # patterns.txt y todos los patterns.*.txt
  python verificar_patterns.py patterns.txt    # solo los archivos indicados
  python verificar_patterns.py --frases        # además, lista todas las frases de ejemplo

No usa micrófono ni ejecuta ningún comando. Las frases de ejemplo salen de las propias
regex (se expanden las alternativas); es una ayuda para revisar, no una prueba de reconocimiento.
Código de salida: 0 sin avisos, 1 con avisos.
"""
import glob
import itertools
import os
import re
import sys
import unicodedata

try:
    import re._parser as sre_parse
except ImportError:  # Python < 3.11
    import sre_parse

HERE = os.path.dirname(os.path.abspath(__file__))
# claves que configuran el programa y no son comandos
CONFIG_KEYS = {
    'vosk_language', 'language', 'spell_prefix', 'spell-prefix', 'spell_prefixes',
    'command_prefix', 'command-prefix', 'command_prefixes', 'literal_word', 'literal-word', 'literal',
    'recognition_engine', 'recognition_engine_command', 'recognition_engine_dictation',
    'speech_engine', 'recognizer', 'engine', 'voice_engine',
}
MAX_SAMPLES = 200


# --- frases de ejemplo a partir de una regex -------------------------------------------------

def _expand(items):
    """Lista de textos que la regex puede producir (aproximado y acotado)."""
    parts = []
    for op, arg in items:
        name = str(op)
        if name == 'LITERAL':
            parts.append([chr(arg)])
        elif name == 'IN':
            chars = []
            for sub_op, sub_arg in arg:
                sub = str(sub_op)
                if sub == 'LITERAL':
                    chars.append(chr(sub_arg))
                elif sub == 'CATEGORY':
                    chars.append(' ' if 'SPACE' in str(sub_arg) else '3')
                elif sub == 'RANGE' and chr(sub_arg[0]).isdigit():
                    chars.append(chr(sub_arg[0]))
            parts.append(chars[:2] or [''])
        elif name == 'CATEGORY':
            parts.append([' ' if 'SPACE' in str(arg) else '3' if 'DIGIT' in str(arg) else 'a'])
        elif name in ('ANY', 'NOT_LITERAL'):
            parts.append(['x'])
        elif name == 'SUBPATTERN':
            parts.append(_expand(arg[-1]))
        elif name == 'BRANCH':
            parts.append([text for alt in arg[1] for text in _expand(alt)])
        elif name in ('MAX_REPEAT', 'MIN_REPEAT'):
            low, _high, sub = arg
            inner = _expand(sub)
            parts.append((['']  if low == 0 else []) + inner)
        # AT (\b, ^, $), ASSERT, ASSERT_NOT, GROUPREF: no aportan texto
    combos = [''.join(c) for c in itertools.islice(itertools.product(*parts), 5000)]
    seen, out = set(), []
    for c in combos:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def sample_phrases(compiled):
    """Frases que la regex acepta, sacadas de ella misma (máximo MAX_SAMPLES)."""
    try:
        texts = _expand(sre_parse.parse(compiled.pattern, compiled.flags))
    except Exception:
        return []
    phrases = []
    for text in texts:
        text = re.sub(r'\s+', ' ', text).strip()
        if text and compiled.search(text) and text not in phrases:
            phrases.append(text)
    return phrases[:MAX_SAMPLES]


# --- lectura de los archivos -----------------------------------------------------------------

def _plain(text):
    """Minúsculas sin tildes ni eñes (para comparar claves)."""
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if not unicodedata.combining(c))


def read_rules(path):
    """[(línea, clave, patrón)] en orden; ignora comentarios y líneas sin '='."""
    rules, omitted = [], set()
    with open(path, 'r', encoding='utf-8') as fh:
        for number, raw in enumerate(fh, 1):
            line = raw.strip()
            declared = re.match(r'#\s*sin[- ]equivalente:\s*(.+)$', line, re.I)
            if declared:
                omitted.update(declared.group(1).replace(',', ' ').split())
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, pattern = line.split('=', 1)
            rules.append((number, key.strip(), pattern.strip(), '=>' in line))
    return rules, omitted


def language_files(args):
    if args:
        return [os.path.abspath(a) for a in args]
    files = [os.path.join(HERE, 'patterns.txt')]
    files += sorted(f for f in glob.glob(os.path.join(HERE, 'patterns.*.txt')) if os.path.basename(f) != 'patterns.txt')
    return [f for f in files if os.path.exists(f)]


def build_assistant(path):
    """Objeto sin __init__ (sin bandeja, micrófono ni tkinter) con las reglas reales de ese archivo."""
    sys.dont_write_bytecode = True
    sys.path.insert(0, HERE)
    import xulia2
    assistant = object.__new__(xulia2.VoiceControlAssistant)
    assistant.commands = assistant._load_patterns_from_file(path)
    assistant._init_command_handlers()
    return assistant


# --- verificaciones --------------------------------------------------------------------------

def check_file(path, base_keys, show_phrases):
    name = os.path.basename(path)
    findings = []
    rules, omitted = read_rules(path)

    seen = {}
    for number, key, pattern, has_arrow in rules:
        if key.lower() in CONFIG_KEYS:
            continue
        if has_arrow and key not in seen:
            continue  # reemplazo del dictado "regex => texto"; el cargador lo lee como clave inofensiva
        if key in seen:
            note = " (línea con '=>': el cargador la lee como comando)" if has_arrow else ''
            findings.append(f"clave repetida '{key}': línea {number}{note} pisa la de la línea {seen[key]}")
        seen.setdefault(key, number)
        try:
            re.compile(pattern, re.I)
        except re.error as exc:
            findings.append(f"regex inválida en '{key}' (línea {number}): {exc}")

    keys = {k for k in seen}
    if base_keys is not None:
        for key in sorted(base_keys - keys - omitted):
            findings.append(f"falta la clave '{key}' (está en patterns.txt)")
        for key in sorted(keys - base_keys):
            findings.append(f"sobra la clave '{key}' (no está en patterns.txt)")

    try:
        assistant = build_assistant(path)
    except Exception as exc:  # faltan dependencias del programa
        findings.append(f"no se pudieron comprobar acciones ni choques entre reglas ({type(exc).__name__}: {exc})")
        return findings, keys

    commands, handlers = assistant.commands, assistant._command_handlers
    for key in commands:
        if key in seen and not handlers.get(key):
            findings.append(f"clave sin acción '{key}': no hay manejador en _init_command_handlers")

    order = [k for k in commands if handlers.get(k)]
    clashes = {}
    for key in order:
        if key not in seen:
            continue  # regla que el programa añade sola si falta en el archivo
        phrases = sample_phrases(commands[key])
        if show_phrases:
            print(f"  [{key}] " + ' | '.join(phrases[:12]))
        for phrase in phrases:
            winner = next((k for k in order if commands[k].search(phrase)), None)
            # 'tecla<ciudad>' y '<ciudad>' pulsan la misma letra: no es un choque
            if winner and winner != key and _plain(key) != 'tecla' + _plain(winner):
                clashes.setdefault((key, winner), []).append(phrase)
    for (key, winner), phrases in sorted(clashes.items()):
        findings.append(f"'{key}' queda tapada por '{winner}' (va antes): "
                        + ', '.join(repr(p) for p in phrases[:3]) + (f" y {len(phrases) - 3} más" if len(phrases) > 3 else ''))
    return findings, keys


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    show_phrases = '--frases' in sys.argv[1:]
    files = language_files(args)
    if not files:
        print('No hay archivos de patrones.')
        return 1
    base_keys, total = None, 0
    for path in files:
        print(f"== {os.path.basename(path)}")
        use_base = base_keys if os.path.basename(path) != 'patterns.txt' else None
        findings, keys = check_file(path, use_base, show_phrases)
        if os.path.basename(path) == 'patterns.txt':
            base_keys = keys
        for finding in findings:
            print('  - ' + finding)
        if not findings:
            print('  sin avisos')
        total += len(findings)
    print(f"\n{total} aviso(s)")
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
