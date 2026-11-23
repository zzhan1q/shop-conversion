import csv
import io
import json
import sqlite3
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = "https://archive.ics.uci.edu/dataset/468/online%2Bshoppers%2Bpurchasing%2Bintention%2Bdataset"
DATA = "https://archive.ics.uci.edu/static/public/468/online+shoppers+purchasing+intention+dataset.zip"
MONTHS = {
    "Feb": "Фев",
    "Mar": "Мар",
    "May": "Май",
    "June": "Июн",
    "Jul": "Июл",
    "Aug": "Авг",
    "Sep": "Сен",
    "Oct": "Окт",
    "Nov": "Ноя",
    "Dec": "Дек",
}
VISITORS = {
    "Returning_Visitor": "Вернувшиеся",
    "New_Visitor": "Новые",
    "Other": "Другой тип",
}
BOOL = {"TRUE": 1, "FALSE": 0}


def load():
    folder = ROOT / ".cache"
    folder.mkdir(exist_ok=True)
    file = folder / "source.zip"
    if not file.exists():
        with urllib.request.urlopen(DATA, timeout=65) as r:
            data = r.read()
        if not zipfile.is_zipfile(io.BytesIO(data)):
            raise ValueError("UCI did not return a ZIP archive")
        file.write_bytes(data)
    with zipfile.ZipFile(file) as z, z.open("online_shoppers_intention.csv") as raw:
        return [
            (
                a["Month"],
                a["VisitorType"],
                BOOL[a["Weekend"].upper()],
                BOOL[a["Revenue"].upper()],
            )
            for a in csv.DictReader(io.TextIOWrapper(raw, encoding="utf8"))
        ]


def main():
    data = load()
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE sessions(month TEXT NOT NULL, visitor TEXT NOT NULL, weekend INTEGER NOT NULL CHECK(weekend IN (0,1)), purchased INTEGER NOT NULL CHECK(purchased IN (0,1)))"
    )
    db.executemany("INSERT INTO sessions VALUES (?,?,?,?)", data)
    db.executescript((ROOT / "analysis.sql").read_text(encoding="utf8"))
    out = [dict(x) for x in db.execute("SELECT * FROM conversion ORDER BY cut,segment")]
    n = len(data)
    buys = sum(a[3] for a in data)
    if (n, buys) != (12330, 1908):
        raise ValueError(f"Unexpected session or purchase totals: {n}, {buys}")
    cuts = {
        k: {x["segment"]: x for x in out if x["cut"] == k}
        for k in ("month", "visitor", "weekend")
    }
    expected = {
        "month": set(MONTHS),
        "visitor": set(VISITORS),
        "weekend": {"Weekend", "Weekday"},
    }
    for name, cut in cuts.items():
        missing = expected[name] - cut.keys()
        unexpected = cut.keys() - expected[name]
        if missing or unexpected:
            raise ValueError(
                f"{name}: missing {sorted(missing)}, unexpected {sorted(unexpected)}"
            )
        if (
            sum(x["sessions"] for x in cut.values()) != n
            or sum(x["purchases"] for x in cut.values()) != buys
        ):
            raise ValueError(f"Counts do not reconcile in {name}")
        if abs(sum(x["traffic_share"] for x in cut.values()) - 1) >= 1e-9:
            raise ValueError(f"Traffic shares do not sum to one in {name}")
    if not all(
        0 <= a["purchases"] <= a["sessions"]
        and abs(a["conversion"] - a["purchases"] / a["sessions"]) < 1e-12
        for a in out
    ):
        raise ValueError("Invalid segment conversion")

    def fmt(x):
        return f"{x:,}".replace(",", " ")

    def group(label, cut, labels, typ):
        d = cuts[cut]
        rows = list(labels.items())
        big = max(d.values(), key=lambda x: x["sessions"])
        champion = max(d.values(), key=lambda x: x["conversion"])
        return {
            "name": label,
            "kpis": [
                {
                    "label": "Максимум конверсии",
                    "value": f"{labels[champion['segment']]} · {champion['conversion']:.1%}",
                },
                {
                    "label": "Максимум трафика",
                    "value": f"{labels[big['segment']]} · {fmt(big['sessions'])}",
                },
                {"label": "Сессий с покупкой", "value": fmt(buys)},
            ],
            "charts": [
                {
                    "title": "Конверсия в покупку",
                    "type": typ,
                    "unit": "% сессий",
                    "rows": [
                        {"label": v, "value": round(d[k]["conversion"] * 100, 2)}
                        for k, v in rows
                    ],
                },
                {
                    "title": "Объём трафика",
                    "type": typ,
                    "unit": "сессий",
                    "rows": [{"label": v, "value": d[k]["sessions"]} for k, v in rows],
                },
            ],
        }

    a, b = (cuts["visitor"][k] for k in ("New_Visitor", "Returning_Visitor"))
    nov = cuts["month"]["Nov"]
    may = cuts["month"]["May"]
    result = {
        "title": "Конверсия интернет-магазина",
        "eyebrow": "02 / SQL · продуктовые метрики",
        "subtitle": "Online Shoppers Purchasing Intention · UCI",
        "question": "Где различаются доля покупок и объём трафика, и какие сегменты стоит разобрать прежде всего?",
        "method": [
            "Зерно — одна сессия. Revenue — признак покупки, не денежная сумма.",
            "Конверсия = сессии с Revenue=TRUE / все сессии сегмента. Объём и долю показываем вместе.",
            "SQL строит три независимые разбивки: месяц, тип посетителя, будни/выходные. Итого внутри каждой разбивки совпадает с исходной таблицей.",
        ],
        "findings": [
            f"Общая конверсия — {buys / n:.2%} ({fmt(buys)} из {fmt(n)} сессий).",
            f"Новые посетители конвертировались в {a['conversion']:.2%} сессий против {b['conversion']:.2%} у вернувшихся; у вернувшихся больше покупок в штуках ({fmt(b['purchases'])} против {fmt(a['purchases'])}).",
            f"Ноябрь: {nov['conversion']:.2%} конверсии при {fmt(nov['sessions'])} сессиях. Май: {may['conversion']:.2%} при {fmt(may['sessions'])} сессиях.",
        ],
        "limits": [
            "Это наблюдения, а не эксперимент: состав и источники трафика могут отличаться.",
            "В файле нет января и апреля; отсутствие месяца не трактуем как ноль. Нет последовательности событий, поэтому воронку и отток по шагам не оцениваем.",
            "Выборка собрана для исследования и не обязана повторять структуру полного трафика сайта. Малые сегменты сильнее реагируют на случайные колебания.",
        ],
        "action": "Разбить майский и ноябрьский трафик по типу посетителя и коду источника, прежде чем связывать разницу с изменениями на сайте.",
        "sources": [
            {
                "name": "Sakar & Kastro (2018), UCI Online Shoppers Purchasing Intention, CC BY 4.0",
                "url": SOURCE,
            }
        ],
        "groups": [
            group("Месяцы", "month", MONTHS, "bar"),
            group("Тип посетителя", "visitor", VISITORS, "bar"),
            group(
                "Календарь",
                "weekend",
                {"Weekday": "Будни", "Weekend": "Выходные"},
                "bar",
            ),
        ],
        "checks": [
            "12 330 сессий и 1 908 покупок совпадают с UCI",
            "Все покупки и сессии сохранены в каждой разбивке",
            "Каждая доля пересчитана из числителя и знаменателя",
        ],
    }
    with (ROOT / "summary.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    (ROOT / "case.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )
    print(n, buys)


if __name__ == "__main__":
    main()
