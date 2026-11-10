#!/usr/bin/env bash
#
# Install the CompChemKit skills into an agent's skills directory.
#
# Every methods/<skill>/ folder that contains a SKILL.md is installed into the destination
# directory (default: ~/.dsh/skills), plus the knowledge/ knowledge base as one skill named by
# the `name:` field of knowledge/SKILL.md. The default action is a copy; --link uses a symlink
# and falls back to a copy if symlinks are unavailable.
#
# An existing skill directory in the destination is never deleted implicitly:
#   * without --force it is skipped with a warning;
#   * with --force the replacement is announced and you must confirm at the prompt.
# A non-interactive run therefore never deletes anything.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${HOME}/.dsh/skills"
LINK=0
FORCE=0

usage() {
    cat <<'EOF'
CompChemKit skill installer

Usage: ./install.sh [options]

  --dest DIR   Install into DIR (default: ~/.dsh/skills)
  --link       Symlink each skill with ln -s; falls back to a copy if linking fails
  --force      Allow replacing an existing skill directory (asks for confirmation)
  -h, --help   Show this help

Every methods/<skill>/ folder containing a SKILL.md is installed, plus the knowledge/ knowledge
base as one skill (named by the `name:` field of knowledge/SKILL.md).
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dest)
            if [ "$#" -lt 2 ]; then
                echo "install.sh: --dest needs a directory" >&2
                exit 2
            fi
            DEST="$2"
            shift 2
            ;;
        --dest=*) DEST="${1#--dest=}"; shift ;;
        --link) LINK=1; shift ;;
        --force) FORCE=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *)
            echo "install.sh: unknown option '$1' (try --help)" >&2
            exit 2
            ;;
    esac
done

if [ -z "$DEST" ]; then
    echo "install.sh: destination is empty" >&2
    exit 2
fi

# ---- discover skills -------------------------------------------------------
# methods/<skill>/ is one skill per folder (folder name = skill name). knowledge/ is a single
# knowledge-base skill: its folder name is fixed ("knowledge"), so its skill name comes from the
# `name:` field of its SKILL.md.
shopt -s nullglob
skill_dirs=()
skill_names=()
for dir in "$REPO_ROOT"/methods/*/; do
    if [ -f "${dir}SKILL.md" ]; then
        skill_dirs+=("${dir%/}")
        skill_names+=("$(basename "${dir%/}")")
    fi
done
if [ -f "$REPO_ROOT/knowledge/SKILL.md" ]; then
    knowledge_name="$(sed -n 's/^name:[[:space:]]*//p' "$REPO_ROOT/knowledge/SKILL.md" \
        | head -n 1 | tr -d '\r' | sed 's/[[:space:]]*$//')"
    if [ -z "$knowledge_name" ]; then
        echo "warning: knowledge/SKILL.md has no 'name:' field; installing it as 'knowledge'." >&2
        knowledge_name="knowledge"
    fi
    skill_dirs+=("$REPO_ROOT/knowledge")
    skill_names+=("$knowledge_name")
fi
shopt -u nullglob

if [ "${#skill_dirs[@]}" -eq 0 ]; then
    echo "install.sh: no skills found (no methods/*/SKILL.md and no knowledge/SKILL.md)" >&2
    exit 1
fi

# ---- prepare destination ---------------------------------------------------
if ! mkdir -p "$DEST"; then
    echo "install.sh: cannot create destination '$DEST'" >&2
    exit 1
fi
DEST="$(cd "$DEST" && pwd)"

echo "Installing from: $REPO_ROOT"
echo "Destination:     $DEST"
echo

# ---- install ---------------------------------------------------------------
installed=0
skipped=0
printf '%-26s %-10s %s\n' "SKILL" "ACTION" "DESTINATION"
printf '%-26s %-10s %s\n' "--------------------------" "----------" "---------------------------------"

for index in "${!skill_dirs[@]}"; do
    src="${skill_dirs[$index]}"
    name="${skill_names[$index]}"
    target="$DEST/$name"

    if [ -e "$target" ] || [ -L "$target" ]; then
        echo "Existing target: $target"
        echo "  would be replaced by: $src"

        if [ "$FORCE" -ne 1 ]; then
            echo "warning: skipped '$name': target already exists (use --force to replace it)" >&2
            printf '%-26s %-10s %s\n' "$name" "skipped" "$target"
            skipped=$((skipped + 1))
            continue
        fi

        answer=""
        if [ -t 0 ] && [ -t 1 ]; then
            printf "Delete and replace '%s'? [y/N] " "$target"
            read -r answer || answer=""
        fi
        case "$answer" in
            y|Y|yes|YES|Yes) ;;
            *)
                echo "warning: skipped '$name': replacement not confirmed; non-interactive runs never delete." >&2
                printf '%-26s %-10s %s\n' "$name" "skipped" "$target"
                skipped=$((skipped + 1))
                continue
                ;;
        esac

        case "$target" in
            "$DEST"/*) rm -rf -- "$target" ;;
            *)
                echo "error: refusing to delete '$target' (outside $DEST)" >&2
                skipped=$((skipped + 1))
                continue
                ;;
        esac
    fi

    action="copy"
    if [ "$LINK" -eq 1 ]; then
        if ln -s "$src" "$target" 2>/dev/null; then
            action="link"
        else
            echo "warning: symlink failed for '$name'; falling back to copy." >&2
        fi
    fi
    if [ "$action" = "copy" ]; then
        if ! cp -R "$src" "$target"; then
            echo "error: failed to copy '$name' to '$target'" >&2
            skipped=$((skipped + 1))
            continue
        fi
    fi

    printf '%-26s %-10s %s\n' "$name" "$action" "$target"
    installed=$((installed + 1))
done

# ---- report ----------------------------------------------------------------
echo
echo "Installed $installed skill(s) into $DEST"
if [ "$skipped" -gt 0 ]; then
    echo "warning: skipped $skipped skill(s)" >&2
fi
exit 0
