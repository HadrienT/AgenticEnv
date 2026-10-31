def word_count(text):
    return len(text.split(" "))


def slugify(title):
    return title.lower().replace(" ", "-")


def parse_csv_line(line):
    return line.split(",")


def retry(fn, attempts):
    for _ in range(attempts):
        try:
            return fn()
        except Exception:
            pass
