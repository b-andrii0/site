# Учебный сайт «Containers op RHEL 10»

Статический сайт (HTML/CSS/JS) из Word-глав в `docs/`. Без серверной части, работает на GitHub Pages и офлайн.

## Самый короткий путь

1. Установи Python 3.9+ (https://www.python.org, галочка «Add python.exe to PATH»).
2. Положи главы в `docs/` (`0 Titel.docx`, `1 Titel.docx`, …).
3. Двойной клик по **`bouw.bat`** → готовы `site/` и `dist/cursus-offline.zip`.
4. Открой **`bouwrapport.md`** — там всё, что стоит проверить глазами.

## Что в папке

| Что | Зачем |
|---|---|
| `docs/` | главы: имя начинается с номера и пробела — `9 Nieuwe titel.docx` (номер = порядок) |
| `build.py` | конвертер docx → сайт |
| `bouw.bat` | двойной клик = `pip install` + `python build.py` |
| `ocr-voorstel.bat` | двойной клик = читать команды с новых скриншотов (см. ниже) |
| `test_site.py` | проверка готового сайта (запускается автоматически после сборки) |
| `template/` | шаблон страницы, стили (`assets/site.css`), скрипты (`assets/site.js`, `assets/extra.js`) |
| `afbeelding-commandos.json` | команды со скриншотов (ключ = `глава-номер картинки`, напр. `"4-042"`) |
| `toestel-correcties.json` | устройство для конкретных команд без промпта |
| `spiekbrief/deel_*.json` | содержимое шпаргалки (если есть → страница `spiekbrief.html`) |
| `bouwrapport.md` | отчёт последней сборки |
| `site/` | готовый сайт · `dist/cursus-offline.zip` — офлайн-версия |

## Новая глава — пошагово

1. Сохрани в Word как `.docx`, имя `9 Titel.docx`, закрой Word.
2. `bouw.bat` (или `python build.py`).
3. Смотри `bouwrapport.md`:
   - **Команды без промпта** → по умолчанию «RHEL VM · serverXX». Если это другое устройство — допиши в
     `toestel-correcties.json`: `"начало команды": "Windows host · PowerShell"`.
   - **Предупреждения**: заголовок прыгает уровнем (Kop2 → Kop4), вывод слипся с командой в одной строке Word.
   - Внизу консоли — результат автопроверки (`Fouten: 0` = всё хорошо).
4. Команды со скриншотов: двойной клик `ocr-voorstel.bat` → файл `afbeelding-commandos.voorstel.json`.
   Проверь (OCR путает `0/O`, `l/1`, `-/—`) и перенеси нужное в `afbeelding-commandos.json`
   (или `python build.py --ocr --ocr-overnemen` — перенесёт всё сразу и пересоберёт).

### Как скрипт понимает Word (чтобы глава собралась без ошибок)

- Заголовки: стили **Kop1** (название главы, один раз), **Kop2/Kop3/Kop4/Kop5**. Нумерация 9.1, 9.1.1 ставится сама.
- Команды/вывод: абзацы шрифтом **Cascadia Code / Consolas / Courier** (как в оригинале).
- Устройство берётся из промпта: `student@serverXX:~$`, `[student@clientXX ~]$`, `[root@abc123 /]#` (контейнер),
  `PS C:\…>` (Windows PowerShell), `C:\…>` (CMD), `MariaDB [db]>`.
- Строки после `nano файл` / `cat > файл` считаются содержимым файла («Bestandsinhoud», копируется целиком).
- YAML/Containerfile-блоки без промпта → «Bestandsinhoud». Остальной текст без промпта → «Uitvoer» (свёрнут).
- Команды с `\` в конце и heredoc (`<<EOF`) склеиваются в одну.

## Залить на GitHub Pages

1. github.com → **New repository** → имя, например `cursus` → **Public** (для Private-репо Pages платные; сайт всё равно скрыт от поисковиков).
2. Залей **содержимое папки `site/`** в корень репозитория (кнопка «Add file → Upload files», перетащить всё) или через git:
   ```
   cd site
   git init
   git add .
   git commit -m "Cursus-site"
   git branch -M main
   git remote add origin https://github.com/<gebruiker>/cursus.git
   git push -u origin main
   ```
3. **Settings → Pages → Source: Deploy from a branch → Branch: `main` / `(root)` → Save.**
4. Через 1–2 минуты: `https://<gebruiker>.github.io/cursus/`.

Обновление: `bouw.bat` → снова загрузить содержимое `site/` (git: `git add . && git commit -m "update" && git push`).

## Скрыт от поисковиков

- На каждой странице `<meta name="robots" content="noindex, nofollow, noarchive">` — главное, Google это соблюдает.
- `robots.txt` (`Disallow: /`) в корне сайта. Для адреса `<gebruiker>.github.io/cursus/` поисковики читают robots.txt
  только из корня домена, поэтому там работает именно `noindex`.
- `.nojekyll` отключает обработку Jekyll на GitHub.

## Офлайн

Распаковать `cursus-offline.zip` → открыть `cursus/index.html`. Всё локально: без CDN и внешних шрифтов, поиск работает и через `file://`.
