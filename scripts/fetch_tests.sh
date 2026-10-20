#!/bin/bash
# Скачивает тесты AtCoder для Python-задач ConDefects вместо Test.zip.
#
# Источник: зеркало официальных тестов AtCoder github.com/conlacda/atcoder-testcases
# (одна ветка на контест). Качаются только папки нужных задач (sparse checkout).
# Результат: data/raw/Test/<contest>/<LETTER>/{in,out}/ — этот путь понимает `make data`.
#
# Повторный запуск продолжает с места остановки: готовые контесты помечены
# файлами data/raw/Test/.done_<contest>. Нужны git и сеть; запускается на хосте.
set -u
REPO=$(cd "$(dirname "$0")/.." && pwd)
CODE=$REPO/data/raw/ConDefects/Code
OUT=$REPO/data/raw/Test
WORK=$REPO/data/raw/.fetch_work
MIRROR=https://github.com/conlacda/atcoder-testcases.git
JOBS=${JOBS:-4}

# Список задач берётся из ConDefects: клонируем на коммите из configs/data.yaml, если клона нет
if [ ! -d "$CODE" ]; then
  url=$(awk '/^repo_url:/{print $2}' "$REPO/configs/data.yaml")
  commit=$(awk '/^commit:/{print $2}' "$REPO/configs/data.yaml")
  echo "Клонирую ConDefects ($commit)..."
  git clone -q "$url" "$REPO/data/raw/ConDefects" && git -C "$REPO/data/raw/ConDefects" checkout -q "$commit" || exit 1
fi
mkdir -p "$OUT" "$WORK"

fetch_contest() {
  c=$1; shift
  [ -f "$OUT/.done_$c" ] && return 0
  d=$WORK/$c; rm -rf "$d"
  paths=""
  for L in "$@"; do paths="$paths $c/$L"; done
  if git clone -q --depth 1 --filter=blob:none --no-checkout --branch "$c" "$MIRROR" "$d" 2>>"$WORK/err_$c.log" \
     && git -C "$d" sparse-checkout set --no-cone $paths 2>>"$WORK/err_$c.log" \
     && git -C "$d" checkout -q "$c" 2>>"$WORK/err_$c.log"; then
    for L in "$@"; do
      if [ -d "$d/$c/$L" ]; then
        mkdir -p "$OUT/$c" && rm -rf "$OUT/$c/$L" && mv "$d/$c/$L" "$OUT/$c/$L"
      fi
    done
    touch "$OUT/.done_$c"; echo "ok   $c"
  else
    echo "FAIL $c (см. $WORK/err_$c.log)"
  fi
  rm -rf "$d"
}
export -f fetch_contest; export OUT WORK MIRROR

# План: "<contest> <LETTER>..." для каждой Python-задачи; задачи H в ABC у AtCoder лежат в папке Ex
for p in "$CODE"/*/Python; do
  t=$(basename "$(dirname "$p")"); c=${t%_*}; L=$(echo "${t##*_}" | tr a-z A-Z)
  echo "$c $L"; [ "$L" = "H" ] && echo "$c Ex"
done | sort -u | awk '{a[$1]=a[$1]" "$2} END{for(k in a) print k a[k]}' | sort > "$WORK/plan.txt"

total=$(wc -l < "$WORK/plan.txt")
done_before=$(ls -a "$OUT" | grep -c '^\.done_')
echo "Контестов: $total, уже скачано: $done_before. Параллельно: $JOBS."
xargs -P "$JOBS" -L 1 bash -c 'fetch_contest "$@"' _ < "$WORK/plan.txt"
echo "Готово: $(ls -a "$OUT" | grep -c '^\.done_') из $total. Контесты, которых нет в зеркале, отсеются в make data как no_tests."
