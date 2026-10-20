# Структура ConDefects (изучено на коммите `43f0834a82c5e3bc4516c079fe7765f63b1a15cd`)

## Корень репозитория

```
ConDefects/
├── Code/                 # 1155 задач (Java + Python), 985 задач имеют папку Python/
├── ConDefects.py         # CLI авторов (info / checkout / run / coverage)
├── Tool/                 # Checkout.py, Info.py, RunTest.py + pickle-файлы date, difficulty, path2Code
├── Lib/                  # jacoco для Java
├── date.txt              # "<task> <YYYY-MM-DD>" по строке на задачу (1156 строк)
└── difficulty.txt        # "<task> <int>" по строке на задачу (1156 строк)
```

`Test.zip` в git отсутствует (слишком большой) — скачивается вручную по ссылкам из README
и кладётся в `data/raw/Test.zip`.

## Программы

```
Code/<task>/Python/<program_id>/
├── faultyVersion.py      # программа с ошибкой
├── correctVersion.py     # исправленная версия
└── faultLocation.txt     # один номер строки (с 1), без перевода строки
```

- `<task>` — `<contest>_<letter>`, например `abc323_c`.
- `<program_id>` — номер посылки AtCoder.
- Python: 2864 программы. Во всех `faultLocation.txt` ровно одно целое число.
- Исправленная строка (`fixed_line`) в разметке отдельно не хранится: берётся из
  `correctVersion.py` по тому же номеру строки (ошибки однострочные).
- Часть программ — Python 2 (`print x`); авторы распознают их по подстроке `"print "`,
  мы — по `ast.parse`.

## Тесты (`Test.zip`)

Из `Tool/RunTest.py`: архив распаковывается в `Test/`, тесты задачи лежат в

```
Test/<contest>/<LETTER>/in/<name>
Test/<contest>/<LETTER>/out/<name>
```

`<LETTER>` — буква задачи в верхнем регистре (`abc323_c` → `Test/abc323/C/`).
Если такой папки нет, авторы используют `Test/<contest>/Ex/` (задачи `_h`/`Ex` в ABC).
Ожидаемый вывод — файл с тем же именем в соседней папке `out/`.

Авторы сравнивают вывод построчно и строго; мы используем сравнение по токенам с допуском
для вещественных чисел (spec.md, раздел 6.2).
